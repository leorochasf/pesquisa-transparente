"""Camada de evidencia (lastro): download de PDFs + manifesto + screenshot de folha.

Orquestra o que ja existe (`anexos.listar_anexos`/`anexos.baixar_anexo`, SEM
altera-los) para produzir o dossie em disco descrito no blueprint
(`AUDITORIA/refatoracao/04-blueprint.md` §2):

    data/casos/<caso_id>/
      manifesto.jsonl                 # 1 evidencia por linha, append-only (§2.3)
      evidencias_pendentes.jsonl      # PDFs nao baixados por teto (indice p/ expansao)
      evidencias/
        <municipio>/
          <secao>/<numero>_anexoN.pdf    # PDFs de contratos/licitacoes/dispensas (§2.1)
          folha/<NOME>_<ano>-<mes>.png    # print da folha filtrada (§2.2)
          folha/<NOME>_<ano>-<mes>.json   # dado estruturado correspondente ao print

Teto de PDFs por caso (Decisao 1 do dono, `05-decisoes-do-dono.md`): baixa tudo
automaticamente ate `TETO_PDFS_CASO`; o excedente e registrado no indice de
pendentes para expansao posterior, sem derrubar o resto do caso.

Screenshot de folha (Decisao 2): a prova por competencia e screenshot + JSON
dos valores + URL da secao + sha256 — nunca um link direto ao holerite (nao
existe, doc 02 §4). O JSON vem do MESMO canal server-side ja usado pela busca
por entidade (`entidade._grupo_folha`, httpx, confiavel nos 6 municipios); o
print vem via Playwright (`nucleo/client.py::NucleoClient`). O widget de
periodo (ano/mes) do portal so foi CONFIRMADO AO VIVO em Senador Canedo
(botao `.today.icon-date` + `.datepickerbt-months`, ver `_selecionar_periodo`);
nos demais municipios o print sai com o periodo padrao do portal e um aviso
explicito acompanha o retorno — nunca se finge ter forcado um periodo que nao
foi confirmado (regra anti-alucinacao do projeto).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from ..config import settings
from ..db import DB
from ..municipios import Municipio, get as get_mun
from . import anexos, capacidades, casos, entidade
from .client import NucleoClient
from .routes import resolve as resolver_rotas

logger = logging.getLogger(__name__)

# Teto de PDFs baixados automaticamente por caso (Decisao 1 do dono). O que
# excede vira indice de pendentes (`evidencias_pendentes.jsonl`) para expansao.
TETO_PDFS_CASO = 200

# Pausa entre downloads sequenciais de anexo (consumo respeitoso do portal —
# ver Restricoes do brief: "sem stealth", varredura controlada).
_INTERVALO_DOWNLOAD = 0.15

# Meses abreviados como o widget de periodo do portal os rotula (Senador
# Canedo, confirmado ao vivo — ver `_selecionar_periodo`).
_MESES_PT = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]

# Nome completo do mes como a coluna "Referencia" da tabela de folha exibe
# (ex.: "Marco/2026") — usado para CONFIRMAR que a tabela ja re-renderizou
# para o periodo pedido antes do print (ver nota em `capturar_screenshot_folha`:
# o "chip" de periodo atualiza antes da tabela, entao so checar o nome do
# servidor no corpo da pagina da falso-positivo com dado do periodo ANTERIOR).
_MESES_REFERENCIA_PT = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]

_SANEA_NOME = re.compile(r"[^\w\-]+")


class EvidenciaError(RuntimeError):
    """Falha ao coletar evidencia (download ou screenshot)."""


class EvidenciaIndisponivel(EvidenciaError):
    """Nao ha evidencia a coletar (registro sem anexo, folha sem resultado)."""


class EvidenciaAmbigua(EvidenciaError):
    """A `matricula` informada nao casou com nenhum resultado — nunca escolhe por engano."""


class RegistroIncompleto(EvidenciaError):
    """`registro` esta sem campo(s) que esta secao exige para localizar anexos (F2).

    Nunca falha em silencio: `baixar_evidencias_registro` levanta este erro
    ANTES de bater no portal quando falta `numero` numa secao com anexo (ex.:
    `{'id':'517'}` sem numero — caso real da aceitacao final, doc
    `06-aceitacao-final.md` F2/F1: o portal devolve 0 anexos sem avisar).
    `faltando` e a interface que quem chama usa para devolver uma mensagem
    acionavel em vez de `evidencia_ids: []` mudo.
    """

    def __init__(self, message: str, faltando: list[str]):
        super().__init__(message)
        self.faltando = faltando


# --------------------------------------------------------------------------- #
# Caminhos do dossie em disco (blueprint §2.4)
# --------------------------------------------------------------------------- #


def caminho_caso(caso_id: str) -> Path:
    """Pasta do caso em disco: `data/casos/<caso_id>/`."""
    return settings.DATA_DIR / "casos" / caso_id


def _manifesto_path(caso_id: str) -> Path:
    return caminho_caso(caso_id) / "manifesto.jsonl"


def _pendentes_path(caso_id: str) -> Path:
    return caminho_caso(caso_id) / "evidencias_pendentes.jsonl"


def _evidencias_dir(caso_id: str, slug: str, secao: str) -> Path:
    d = caminho_caso(caso_id) / "evidencias" / slug / secao
    d.mkdir(parents=True, exist_ok=True)
    return d


# --------------------------------------------------------------------------- #
# Manifesto (append-only, 1 evidencia por linha — blueprint §2.3)
# --------------------------------------------------------------------------- #


def ler_manifesto(caso_id: str) -> list[dict[str, Any]]:
    """Le todas as entradas do manifesto do caso (lista vazia se ainda nao existe).

    Tolerante a linha corrompida (ex.: processo morto no meio de um `write` —
    a escrita nao e atomica): pula a linha com um `logger.warning`, nunca
    lanca — um caso nao pode ficar inoperante por causa de UMA linha ruim.
    """
    p = _manifesto_path(caso_id)
    if not p.exists():
        return []
    linhas: list[dict[str, Any]] = []
    for n, linha in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
        linha = linha.strip()
        if not linha:
            continue
        try:
            linhas.append(json.loads(linha))
        except json.JSONDecodeError:
            logger.warning(
                "manifesto.jsonl do caso '%s': linha %d corrompida, ignorada: %r",
                caso_id, n, linha[:200],
            )
    return linhas


def _agora_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _coletado_em_ts(coletado_em: Any) -> float:
    """`coletado_em` do manifesto e ISO (`_agora_iso`); a tabela `evidencias`
    guarda REAL (unix timestamp, mesmo formato de `casos.criado_em` etc. --
    contrato TS `EvidenciaCaso.coletado_em: number`)."""
    if isinstance(coletado_em, str):
        try:
            return datetime.strptime(coletado_em, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            pass
    return time.time()


def _inserir_evidencia_db(banco: DB, caso_id: str, entrada: dict[str, Any]) -> bool:
    """Insere 1 evidencia do manifesto na tabela `evidencias` (W2-F1),
    `INSERT OR IGNORE` por `id` -- chamavel tanto no registro ao vivo quanto
    no backfill (idempotente: reexecutar nao duplica).

    Nunca derruba o chamador: o manifesto.jsonl (fonte de auditoria) ja foi
    gravado antes desta chamada, entao um erro aqui (ex.: `caso_id` orfao, sem
    linha em `casos` -- FK falha) vira warning + `False`, nunca excecao.
    """
    evidencia_id = entrada.get("evidencia_id")
    if not evidencia_id:
        return False
    try:
        with banco._lock, banco.connect() as conn:
            cur = conn.execute(
                """INSERT OR IGNORE INTO evidencias
                   (id, caso_id, item_id, tipo, caminho_local, url_origem,
                    sha256, bytes, content_type, coletado_em)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    evidencia_id,
                    caso_id,
                    entrada.get("item_id") or None,
                    entrada.get("tipo"),
                    entrada.get("caminho_local"),
                    entrada.get("url_origem"),
                    entrada.get("sha256"),
                    entrada.get("bytes"),
                    entrada.get("content_type"),
                    _coletado_em_ts(entrada.get("coletado_em")),
                ),
            )
            conn.commit()
            return cur.rowcount > 0
    except sqlite3.Error as exc:
        logger.warning(
            "Nao foi possivel indexar evidencia '%s' (caso '%s') na tabela evidencias: %s",
            evidencia_id, caso_id, exc,
        )
        return False


def registrar_evidencia(caso_id: str, entrada: dict[str, Any], db: DB | None = None) -> dict[str, Any]:
    """Grava UMA linha no manifesto (append-only) e devolve a entrada completa.

    Atribui `evidencia_id` sequencial (`ev_NNNNNN`) e `coletado_em` (UTC). Nunca
    reescreve nem apaga linhas existentes — o manifesto e uma trilha de
    auditoria imutavel (§2.3): o mesmo sha256 aqui e o que vai no relatorio.

    Quando `db` e informado, TAMBEM indexa a evidencia na tabela `evidencias`
    (W2-F1) -- o manifesto continua sendo a fonte de auditoria; o banco e o
    que `casos.obter_caso` le para devolver `caso.evidencias` na API. Sem
    `db` (uso direto/teste sem caso persistido), so o manifesto e gravado.
    """
    p = _manifesto_path(caso_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    proximo = len(ler_manifesto(caso_id)) + 1
    # Chaves geradas por ULTIMO no merge: `entrada` nunca sobrescreve
    # evidencia_id/caso_id/coletado_em, mesmo se o chamador incluir essas
    # chaves por engano.
    completa = {
        **entrada,
        "evidencia_id": f"ev_{proximo:06d}",
        "caso_id": caso_id,
        "coletado_em": _agora_iso(),
    }
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(completa, ensure_ascii=False) + "\n")
    if db is not None:
        _inserir_evidencia_db(db, caso_id, completa)
    return completa


def backfill_evidencias(db: DB | None = None) -> int:
    """Migracao idempotente (W2-F1): varre `data/casos/*/manifesto.jsonl` de
    TODOS os casos e insere na tabela `evidencias` o que ainda nao esta la
    (`INSERT OR IGNORE` por `id`, ver `_inserir_evidencia_db`). Cobre
    evidencias coletadas antes desta correcao. Chamada no boot da API
    (`busca_go/api.py::lifespan`); reexecutar (2x, ou a cada boot) nao
    duplica nada. Retorna quantas linhas foram efetivamente inseridas nesta
    chamada.
    """
    banco = db or casos.default_db()
    casos_dir = settings.DATA_DIR / "casos"
    if not casos_dir.exists():
        return 0
    inseridas = 0
    for pasta in sorted(casos_dir.iterdir()):
        if not pasta.is_dir():
            continue
        for entrada in ler_manifesto(pasta.name):
            if _inserir_evidencia_db(banco, pasta.name, entrada):
                inseridas += 1
    return inseridas


def contar_pdfs_manifesto(caso_id: str) -> int:
    """Quantos PDFs ja estao registrados no manifesto do caso (base do teto)."""
    return sum(1 for e in ler_manifesto(caso_id) if e.get("tipo") == "pdf")


def ler_pendentes(caso_id: str) -> list[dict[str, Any]]:
    """Indice de anexos NAO baixados por teto (refs para expansao posterior)."""
    p = _pendentes_path(caso_id)
    if not p.exists():
        return []
    return [json.loads(linha) for linha in p.read_text(encoding="utf-8").splitlines() if linha.strip()]


def _registrar_pendentes(caso_id: str, pendentes: list[dict[str, Any]]) -> None:
    """Acrescenta ao indice de pendentes, sem duplicar por `caminho_local`.

    Reexecucoes do mesmo registro que ainda estourem o teto reproduzem os
    mesmos `caminho_local` — sem dedup, o indice (e o relatorio que o lista,
    P5) inflaria a cada chamada.
    """
    if not pendentes:
        return
    conhecidos = {p.get("caminho_local") for p in ler_pendentes(caso_id) if p.get("caminho_local")}
    novos = [p for p in pendentes if p.get("caminho_local") not in conhecidos]
    if not novos:
        return
    p = _pendentes_path(caso_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        for pend in novos:
            f.write(json.dumps({**pend, "registrado_em": _agora_iso()}, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------- #
# Download de PDFs de UM registro (contrato/licitacao/dispensa) — blueprint §2.1
# --------------------------------------------------------------------------- #


def _slug_numero(valor: str) -> str:
    """Numero do registro -> fragmento seguro de nome de arquivo (ex.: '0343/26' -> '0343-26')."""
    limpo = (valor or "registro").strip().replace("/", "-").replace(" ", "-")
    limpo = _SANEA_NOME.sub("", limpo)
    return limpo or "registro"


def _sha256(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _descrever_origem(mun: Municipio, secao: str, ref: str) -> str:
    """Descricao de auditoria da origem do anexo — NUNCA expoe base64/assinatura do `ref`."""
    try:
        dados = anexos._decode_ref(ref)
    except anexos.AnexoIndisponivel:
        return f"{mun.url_base}/api"
    if dados.get("m") == "A":
        return f"{mun.url_base}/api (acao={dados.get('acao', '')})"
    return f"{mun.url_base}/api ({secao}/busca_avancada + URL assinada S3)"


@dataclass
class ResultadoEvidencias:
    """Resultado de `baixar_evidencias_registro`."""

    baixados: list[dict[str, Any]] = field(default_factory=list)
    falhas: list[dict[str, str]] = field(default_factory=list)
    pendentes: list[dict[str, str]] = field(default_factory=list)
    teto_atingido: bool = False


async def baixar_evidencias_registro(
    caso_id: str,
    slug: str,
    secao: str,
    registro: dict[str, Any],
    item_id: str | None = None,
    client: httpx.AsyncClient | None = None,
    db: DB | None = None,
) -> ResultadoEvidencias:
    """Baixa TODOS os anexos de UM registro e grava no manifesto do caso.

    Reusa `anexos.listar_anexos`/`anexos.baixar_anexo` (sem altera-los), em
    SEQUENCIA controlada (nao paraleliza os downloads de um mesmo registro,
    com pausa entre cada um — consumo respeitoso do portal). Respeita o teto
    de `TETO_PDFS_CASO` PDFs por caso (conta o que ja esta no manifesto); o
    excedente vai para o indice de pendentes (`evidencias_pendentes.jsonl`,
    deduplicado por `caminho_local`), sem interromper o restante do caso. Uma
    falha em UM anexo (portal recusou, link expirou) nao derruba os demais —
    vai para `falhas`. Idempotente: a checagem de "ja esta no manifesto"
    acontece ANTES do teto e ANTES de bater na rede — reexecutar para o mesmo
    registro nao rebaixa nada que ja esta em disco, mesmo se o caso ja tiver
    estourado o teto com ESTE registro.

    Args:
        caso_id: identificador do caso (pasta em `data/casos/<caso_id>/`).
        slug, secao: municipio + secao do registro ('contratos'|'licitacoes'|'dispensas').
        registro: identificadores {'id','numero','ano'} — mesmo formato que
            `anexos.listar_anexos` espera (`ref_registro` da busca por entidade).
        item_id: id do item no caso (P2/`casos.py`), gravado no manifesto para
            religar a evidencia ao achado; opcional (uso direto sem P2, ex.: testes).
        client: httpx.AsyncClient injetavel (teste); se None, cria/fecha o proprio.
        db: `DB` injetavel (W2-F1); repassado a `registrar_evidencia` para
            TAMBEM indexar cada evidencia na tabela `evidencias`. Sem `db`, so
            o manifesto e gravado (uso direto/teste sem caso persistido).

    Raises:
        KeyError: municipio nao cadastrado.
        SecaoIndisponivel/AnexoError/PortalError: falha ao sequer LISTAR os
            anexos do registro — propaga (nao ha ResultadoEvidencias parcial
            nesse caso; quem chama decide o que fazer com a secao inteira).
        RegistroIncompleto: `registro` sem `numero` numa secao que expoe
            anexo (F2) — nunca deixa o chamador ler silencio (`baixados:[],
            falhas:[]`) como "sem anexo" quando na verdade faltou informar o
            registro completo.
    """
    mun = get_mun(slug)
    cap = capacidades.resolver(slug, secao)
    if cap.modo_anexo != "sem_anexo":
        # 'numero' e o campo cuja falta reproduz o silencio real da aceitacao
        # final (`{'id':'517'}` -> 0 anexos sem avisar; com 'numero' o mesmo
        # registro baixou 1). 'ano' e enviado quando presente mas nao e
        # exigido aqui — mesmo criterio que `agente/tools.py` (ACEIT-F1) ja
        # valida antes de chegar nesta camada; alinhar evita 2 politicas
        # divergentes para o mesmo dado.
        faltando = [c for c in ("numero",) if not str(registro.get(c) or "").strip()]
        if faltando:
            raise RegistroIncompleto(
                f"Registro incompleto para localizar anexos em '{slug}/{secao}': faltam "
                f"{', '.join(faltando)} (recebido apenas "
                f"{sorted(k for k, v in registro.items() if str(v or '').strip())}). Sem esse "
                "campo o portal pode devolver 0 anexos sem avisar — use o 'ref_registro' "
                "completo que a busca por entidade devolveu para este item.",
                faltando=faltando,
            )
    fechar = client is None
    cli = client or entidade._novo_client()
    resultado = ResultadoEvidencias()
    try:
        lst = await anexos.listar_anexos(slug, secao, registro, client=cli)
        if not lst:
            return resultado
        restante = TETO_PDFS_CASO - contar_pdfs_manifesto(caso_id)
        numero_slug = _slug_numero(str(registro.get("numero") or registro.get("id") or "registro"))
        pasta = _evidencias_dir(caso_id, slug, secao)
        mapa_conhecidos = {e.get("caminho_local"): e for e in ler_manifesto(caso_id)}
        for idx, anexo in enumerate(lst, start=1):
            # `anexos._nome_arquivo` SEMPRE termina o nome em ".pdf" (os 3
            # modos servem PDF), entao o caminho final e computavel ANTES de
            # baixar — permite checar idempotencia (e so DEPOIS o teto e a
            # rede), evitando pendente falso e re-download do que ja esta em
            # disco (achados F1/F4 da revisao P3).
            caminho = pasta / f"{numero_slug}_anexo{idx}.pdf"
            caminho_relativo = caminho.relative_to(caminho_caso(caso_id)).as_posix()
            existente = mapa_conhecidos.get(caminho_relativo)
            if existente is not None:
                # Ja baixado numa execucao anterior (mesmo caminho) — nao
                # duplica o manifesto, nao consome teto, nao bate na rede.
                resultado.baixados.append(existente)
                continue
            if restante <= 0:
                resultado.pendentes.append(
                    {
                        "municipio": slug,
                        "secao": secao,
                        "item_id": item_id or "",
                        "rotulo": anexo["rotulo"],
                        "ref": anexo["ref"],
                        "caminho_local": caminho_relativo,
                    }
                )
                continue
            try:
                blob, _nome_original, ctype = await anexos.baixar_anexo(slug, secao, anexo["ref"], client=cli)
            except anexos.AnexoError as exc:
                resultado.falhas.append({"rotulo": anexo["rotulo"], "erro": str(exc)})
                continue
            caminho.write_bytes(blob)
            entrada = registrar_evidencia(
                caso_id,
                {
                    "item_id": item_id or "",
                    "tipo": "pdf",
                    "municipio": slug,
                    "secao": secao,
                    "rotulo": anexo["rotulo"],
                    "url_origem": _descrever_origem(mun, secao, anexo["ref"]),
                    "caminho_local": caminho_relativo,
                    "sha256": _sha256(blob),
                    "bytes": len(blob),
                    "content_type": ctype,
                },
                db=db,
            )
            mapa_conhecidos[caminho_relativo] = entrada
            resultado.baixados.append(entrada)
            restante -= 1
            await asyncio.sleep(_INTERVALO_DOWNLOAD)
        if resultado.pendentes:
            _registrar_pendentes(caso_id, resultado.pendentes)
            resultado.teto_atingido = True
        return resultado
    finally:
        if fechar:
            await cli.aclose()


# --------------------------------------------------------------------------- #
# Screenshot de folha (nome/matricula + competencia) — blueprint §2.2
# --------------------------------------------------------------------------- #


def _slug_nome(nome: str) -> str:
    limpo = _SANEA_NOME.sub("", (nome or "servidor").strip().upper().replace(" ", "-"))
    return limpo or "SERVIDOR"


async def _selecionar_periodo(page: Any, ano: int, mes: int) -> None:
    """Forca ano/mes no widget de periodo do portal (confirmado ao vivo SO em Senador Canedo).

    Abre o seletor (`.today.icon-date`), navega o ano clicando prev/next e
    lendo o titulo (`.datepickerbt-months th.datepickerbt-switch`) ate casar
    com `ano`, e clica a abreviacao do mes em portugues. `capturar_screenshot_folha`
    so chama esta funcao quando `.today.icon-date` esta presente na pagina
    (deteccao de capacidade — nunca assume o widget existe).

    Raises:
        EvidenciaError: nao conseguiu navegar ate `ano` em ate 30 cliques
            (defesa contra loop infinito, nunca trava o caso).
    """
    await page.click(".today.icon-date")
    await page.wait_for_timeout(400)
    for _ in range(30):
        texto = await page.locator(".datepickerbt-months th.datepickerbt-switch").inner_text()
        atual = int(re.sub(r"\D", "", texto) or 0)
        if atual == ano:
            break
        await page.click(".datepickerbt-months th.prev" if atual > ano else ".datepickerbt-months th.next")
        await page.wait_for_timeout(200)
    else:
        raise EvidenciaError(f"Nao foi possivel navegar ate o ano {ano} no seletor de periodo do portal.")
    rotulo_mes = _MESES_PT[mes - 1]
    await page.click(f'.datepickerbt-months span.month:text-is("{rotulo_mes}")')


def _candidatos_folha_str(itens: list[dict[str, Any]]) -> str:
    return "; ".join(
        f"{it.get('nome') or '(sem nome)'} (matricula {it.get('matricula') or 's/matricula'})"
        for it in itens
    )


def _resolver_servidor_folha(
    itens: list[dict[str, Any]],
    nome: str,
    matricula: str | None,
    ano: int,
    mes: int,
    mun: Municipio,
    *,
    exigir_matricula_unica: bool = False,
) -> list[dict[str, Any]]:
    """Filtra `itens` da folha pela `matricula` informada; nunca cai para os
    homonimos em silencio (achado F5 da revisao P3, reforcado no F5/F6 desta
    missao). `exigir_matricula_unica` (usado por `persistir_e_capturar_folha`,
    F5): sem `matricula`, mais de um servidor distinto para o mesmo `nome` na
    competencia tambem vira `EvidenciaAmbigua` — o fluxo num passo so persiste
    UM item por chamada, nunca escolhe qual homonimo por engano.
    """
    if matricula:
        casaram = [it for it in itens if it.get("matricula") == matricula]
        if not casaram:
            raise EvidenciaAmbigua(
                f"Matricula '{matricula}' nao encontrada entre os resultados de '{nome}' em "
                f"{mes:02d}/{ano} no portal de {mun.nome}. Candidatos encontrados: "
                f"{_candidatos_folha_str(itens)}."
            )
        return casaram
    if exigir_matricula_unica:
        matriculas = {it.get("matricula") for it in itens if it.get("matricula")}
        if len(matriculas) > 1:
            raise EvidenciaAmbigua(
                f"'{nome}' casa com {len(matriculas)} servidores distintos em {mes:02d}/{ano} "
                f"no portal de {mun.nome} — informe 'matricula' para desambiguar. Candidatos "
                f"encontrados: {_candidatos_folha_str(itens)}."
            )
    return itens


@dataclass
class EvidenciaFolha:
    """Resultado de `capturar_screenshot_folha`."""

    png: dict[str, Any]
    json_valores: dict[str, Any]
    avisos: list[str] = field(default_factory=list)
    # Entrada do manifesto do PRINT do JSON estruturado (tipo "json") — evita
    # o chamador ter que varrer `ler_manifesto` atras de `evidencia_relacionada`.
    json_entrada: dict[str, Any] | None = None


async def capturar_screenshot_folha(
    caso_id: str,
    slug: str,
    nome: str,
    ano: int,
    mes: int,
    matricula: str | None = None,
    item_id: str | None = None,
    nucleo_client: NucleoClient | None = None,
    http_client: httpx.AsyncClient | None = None,
    db: DB | None = None,
) -> EvidenciaFolha:
    """Screenshot da folha filtrada (nome/matricula + competencia) + JSON dos valores (Decisao 2).

    Nao existe URL direta para um holerite (doc 02 §4) — o lastro e construido
    pelo app com DUAS coletas independentes da MESMA consulta (nome+ano+mes):
    - JSON dos valores: mesmo canal server-side ja usado pela busca por
      entidade (`entidade._grupo_folha`, httpx) — confiavel nos 6 municipios.
    - Print: Playwright (`NucleoClient`), preenchendo o campo "Buscar por
      Matricula ou Nome" e, onde confirmado ao vivo (Senador Canedo), forcando
      o periodo no widget do portal (`_selecionar_periodo`). Nos demais
      municipios o widget nao foi confirmado; o print sai com o periodo padrao
      do portal e um aviso explicito acompanha o retorno — os VALORES no JSON
      continuam corretos independente disso.

    `nome` aceita nome OU matricula (o campo do portal busca por qualquer um
    dos dois); `matricula` e um filtro ADICIONAL para desambiguar homonimos
    entre os resultados que `nome` trouxe.

    Grava PNG + JSON em `data/casos/<id>/evidencias/<slug>/folha/` e registra
    DUAS linhas no manifesto (tipo `screenshot` + tipo `json`, ligadas por
    `evidencia_relacionada`).

    Args:
        nucleo_client: `NucleoClient` ja iniciado (reusa o browser
            compartilhado do lifespan da API); se None, cria/fecha o proprio.
        http_client: httpx.AsyncClient injetavel (teste); se None, cria/fecha
            o proprio.
        db: `DB` injetavel (W2-F1); repassado a `registrar_evidencia` para
            TAMBEM indexar as evidencias na tabela `evidencias`.

    Raises:
        KeyError: municipio nao cadastrado.
        EvidenciaIndisponivel: nenhum registro de folha para nome+periodo.
        EvidenciaAmbigua: `matricula` informada nao casou com NENHUM dos
            resultados de `nome` — nunca cai silenciosamente para os
            homonimos; o chamador recebe os candidatos (nome+matricula) e
            decide (corrigir a matricula, ou confirmar qual e o servidor).
    """
    mun = get_mun(slug)

    fechar_http = http_client is None
    hcli = http_client or entidade._novo_client()
    try:
        grupo, avisos_busca = await entidade._grupo_folha(hcli, mun, "termo", nome, ano, mes)
    finally:
        if fechar_http:
            await hcli.aclose()
    if not grupo or not grupo["itens"]:
        raise EvidenciaIndisponivel(
            f"Nenhum registro de folha para '{nome}' em {mes:02d}/{ano} no portal de {mun.nome}."
        )
    itens = _resolver_servidor_folha(grupo["itens"], nome, matricula, ano, mes, mun)
    avisos = list(avisos_busca)

    fechar_nc = nucleo_client is None
    ncli = nucleo_client or NucleoClient()
    if ncli._context is None:
        await ncli.start()
    page = await ncli._new_page()
    try:
        url = resolver_rotas(mun, "folha")[0]
        await page.goto(url, wait_until="networkidle", timeout=ncli.timeout_ms)
        try:
            await page.wait_for_selector("table td", timeout=6000)
        except Exception:
            pass
        campo = page.locator("#search:visible").first
        await campo.fill(nome)
        await campo.press("Enter")
        await page.wait_for_timeout(700)
        periodo_forcado = await page.locator(".today.icon-date").count() > 0
        if periodo_forcado:
            await _selecionar_periodo(page, ano, mes)
            # O "chip" de periodo (filtro_ativo_componente) atualiza ANTES da
            # tabela re-renderizar (observado ao vivo) — esperar so pelo nome
            # do servidor da falso-positivo com a linha do periodo ANTERIOR
            # ainda na tela. Espera o texto "<Mes por extenso>/<ano>" (coluna
            # "Referencia") aparecer, que so existe depois do re-render real.
            trecho = f"{_MESES_REFERENCIA_PT[mes - 1]}/{ano}"
        else:
            avisos.append(
                f"O portal de {mun.nome} nao tem o seletor de periodo confirmado; o print "
                f"mostra o periodo padrao exibido pelo portal, nao necessariamente {mes:02d}/{ano} "
                "(os valores no JSON sao do periodo certo, coletados server-side)."
            )
            trecho = nome.strip().upper()[:12]
        try:
            await page.wait_for_function(
                "trecho => document.body.innerText.toUpperCase().includes(trecho.toUpperCase())",
                arg=trecho,
                timeout=10000,
            )
        except Exception:
            avisos.append("Tempo esgotado esperando o portal renderizar o resultado filtrado antes do print.")
        await page.wait_for_timeout(500)
        png_bytes = await page.screenshot(full_page=True)
        source_url = page.url
    except EvidenciaError:
        raise
    except Exception as exc:
        # Erros crus do Playwright (TimeoutError, seletor ausente fora de
        # Senador Canedo etc.) nunca vazam sem virar EvidenciaError — quem
        # chama (ex.: agente/tools.py) so trata essa familia de excecao.
        raise EvidenciaError(f"Falha ao capturar screenshot de folha em '{slug}': {exc}") from exc
    finally:
        await page.close()
        if fechar_nc:
            await ncli.close()

    nome_slug = _slug_nome(nome)
    pasta = _evidencias_dir(caso_id, slug, "folha")
    base = f"{nome_slug}_{ano:04d}-{mes:02d}"
    caminho_png = pasta / f"{base}.png"
    caminho_json = pasta / f"{base}.json"
    caminho_png.write_bytes(png_bytes)
    valores = {"municipio": slug, "nome": nome, "ano": ano, "mes": mes, "itens": itens}
    json_bytes = json.dumps(valores, ensure_ascii=False, indent=2).encode("utf-8")
    caminho_json.write_bytes(json_bytes)

    caso_dir = caminho_caso(caso_id)
    entrada_png = registrar_evidencia(
        caso_id,
        {
            "item_id": item_id or "",
            "tipo": "screenshot",
            "municipio": slug,
            "secao": "folha",
            "rotulo": f"Folha {nome} — {mes:02d}/{ano}",
            "url_origem": source_url,
            "caminho_local": caminho_png.relative_to(caso_dir).as_posix(),
            "sha256": _sha256(png_bytes),
            "bytes": len(png_bytes),
            "content_type": "image/png",
        },
        db=db,
    )
    entrada_json = registrar_evidencia(
        caso_id,
        {
            "item_id": item_id or "",
            "tipo": "json",
            "municipio": slug,
            "secao": "folha",
            "rotulo": f"Folha {nome} — {mes:02d}/{ano} (dados estruturados)",
            "url_origem": source_url,
            "caminho_local": caminho_json.relative_to(caso_dir).as_posix(),
            "sha256": _sha256(json_bytes),
            "bytes": len(json_bytes),
            "content_type": "application/json",
            "evidencia_relacionada": entrada_png["evidencia_id"],
        },
        db=db,
    )
    return EvidenciaFolha(png=entrada_png, json_valores=valores, avisos=avisos, json_entrada=entrada_json)


# --------------------------------------------------------------------------- #
# Fluxo manual de folha num passo so (F5): persiste o item E captura a
# evidencia VINCULADA ao mesmo item_id -- Historia 2 do doc 00.
# --------------------------------------------------------------------------- #


async def persistir_e_capturar_folha(
    caso_id: str,
    slug: str,
    nome: str,
    ano: int,
    mes: int,
    matricula: str | None = None,
    nucleo_client: NucleoClient | None = None,
    http_client: httpx.AsyncClient | None = None,
    db: DB | None = None,
) -> dict[str, Any]:
    """UMA competencia de folha, num passo so (F5/F6, aceitacao final H2):
    busca os valores, PERSISTE o item no caso e captura a evidencia (PNG+JSON
    +manifesto) do MESMO chamado de `capturar_screenshot_folha`, mas ja
    amarrada ao `item_id` recem-persistido -- quantificacao e prova saem
    juntas, sem o jurista precisar de duas chamadas separadas.

    Reusa `capturar_screenshot_folha` (nao reimplementa a captura); so
    acrescenta a resolucao do servidor + a persistencia do item ANTES,
    reaproveitando o mesmo criterio de desambiguacao por matricula
    (`_resolver_servidor_folha`). Sem `matricula` e com mais de um servidor
    distinto casando com `nome` na competencia, nunca escolhe por engano --
    levanta `EvidenciaAmbigua` com os candidatos (nome+matricula), igual a um
    homonimo com matricula incorreta.

    Args:
        db: `DB` injetavel (teste); se None, usa `casos.default_db()` -- a
            MESMA instancia e repassada a `casos.adicionar_item` e a
            `capturar_screenshot_folha` (W2-F1: item e evidencias vinculadas
            no mesmo banco).

    Raises:
        KeyError: municipio nao cadastrado.
        EvidenciaIndisponivel: nenhum registro de folha para nome+periodo.
        EvidenciaAmbigua: homonimos sem `matricula` que desambigue, ou
            `matricula` informada sem match — candidatos na mensagem.
    """
    banco = db or casos.default_db()
    mun = get_mun(slug)
    fechar_http = http_client is None
    hcli = http_client or entidade._novo_client()
    try:
        grupo, avisos_busca = await entidade._grupo_folha(hcli, mun, "termo", nome, ano, mes)
        if not grupo or not grupo["itens"]:
            raise EvidenciaIndisponivel(
                f"Nenhum registro de folha para '{nome}' em {mes:02d}/{ano} no portal de {mun.nome}."
            )
        casaram = _resolver_servidor_folha(
            grupo["itens"], nome, matricula, ano, mes, mun, exigir_matricula_unica=True
        )
        item_persistido = casaram[0]
        item_id = casos.adicionar_item(caso_id, slug, "folha", item_persistido, db=banco)
        matricula_resolvida = matricula or item_persistido.get("matricula") or None
        resultado_evidencia = await capturar_screenshot_folha(
            caso_id,
            slug,
            nome,
            ano,
            mes,
            matricula=matricula_resolvida,
            item_id=item_id,
            nucleo_client=nucleo_client,
            http_client=hcli,
            db=banco,
        )
    finally:
        if fechar_http:
            await hcli.aclose()
    return {
        "item_id": item_id,
        "item": item_persistido,
        "evidencia_png_id": resultado_evidencia.png["evidencia_id"],
        "evidencia_json_id": resultado_evidencia.json_entrada["evidencia_id"] if resultado_evidencia.json_entrada else None,
        "avisos": avisos_busca + resultado_evidencia.avisos,
    }


__all__ = [
    "TETO_PDFS_CASO",
    "EvidenciaError",
    "EvidenciaIndisponivel",
    "EvidenciaAmbigua",
    "RegistroIncompleto",
    "ResultadoEvidencias",
    "EvidenciaFolha",
    "caminho_caso",
    "ler_manifesto",
    "registrar_evidencia",
    "backfill_evidencias",
    "contar_pdfs_manifesto",
    "ler_pendentes",
    "baixar_evidencias_registro",
    "capturar_screenshot_folha",
    "persistir_e_capturar_folha",
]
