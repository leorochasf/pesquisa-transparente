"""Cabeca (Gemini 3 Flash): planeja, despacha subtarefas ao worker e redige o
relatorio final (blueprint `AUDITORIA/refatoracao/04-blueprint.md` §6.1,
§6.3). Unico componente que ve o CASO INTEIRO.

Decisoes de implementacao (registradas aqui, nao mudam a arquitetura decidida
pelo dono):

1. **Validacao deterministica.** O guardrail §6.2 #3 ("a cabeca valida o
   resultado do worker contra o manifesto") e feito em `_validar_evidencias`
   conferindo, em CODIGO, se cada `evidencia_id` que o worker afirmou existe
   de fato no `manifesto.jsonl` -- nao pedindo a outra chamada de LLM para
   "confirmar" (que poderia ela mesma alucinar a confirmacao). E o que torna
   a garantia "nunca dado inventado" TESTAVEL sem rede.
2. **Mesmo template do P5.** `nucleo/relatorio.py` (P5) ja monta o
   `relatorio.md` deterministico (cabecalho, achados, quantificacao, indice
   de evidencias) a partir do MESMO caso/manifesto -- blueprint §5: "a versao
   do agente (P4) e a versao deterministica (P5) usam o mesmo template". Em
   vez de duplicar essa formatacao, `redigir_relatorio` chama
   `relatorio.gerar_relatorio_markdown` (consumido como esta, sem alteracao)
   e SO troca a secao "Sintese" pelo paragrafo redigido pela cabeca (LLM) e
   acrescenta as lacunas de subtarefa do agente a secao "Lacunas e
   ressalvas".
3. **Saneamento numerico da sintese (review R4, F2).** A validacao
   deterministica de #1 so cobria `evidencia_id`; o TEXTO livre do `resumo`
   do worker (que alimenta o contexto da sintese) nao era cruzado contra
   nada. `_saneiar_sintese` agora confere TODO numero que a sintese citar
   (contagem, valor, data, sha256) contra `_fonte_estruturada` (itens do
   caso + manifesto) -- o que nao aparecer, verbatim, nos dados persistidos
   vira `[não verificado]`. Erra para o lado conservador de proposito: um
   numero legitimo com formatacao diferente tambem e marcado, mas nenhum
   numero inventado passa sem marca.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from ..nucleo import casos, evidencia, relatorio
from .log import registrar_tool_call
from .openrouter import CustoAcumulado, OpenRouterClient, OpenRouterError
from .worker import ResultadoSubtarefa, executar_subtarefa

logger = logging.getLogger(__name__)


class SemPlano(RuntimeError):
    """A cabeca nao conseguiu decompor o caso em nenhuma subtarefa."""


@dataclass
class Lacuna:
    """Subtarefa que NAO produziu resultado com lastro (guardrail §6.2 #3:
    falhou 2x -> vira lacuna explicita, nunca dado inventado)."""

    subtarefa_id: str
    descricao: str
    motivo: str


@dataclass
class ResultadoInvestigacao:
    caso_id: str
    subtarefas_executadas: list[ResultadoSubtarefa] = field(default_factory=list)
    lacunas: list[Lacuna] = field(default_factory=list)
    relatorio_md: str = ""
    relatorio_path: str = ""
    custo: CustoAcumulado = field(default_factory=CustoAcumulado)
    teto_atingido: bool = False


# --------------------------------------------------------------------------- #
# Planejamento (cabeca decompoe o caso em subtarefas fechadas -- §6.1)
# --------------------------------------------------------------------------- #

_SYSTEM_PLANEJAMENTO = (
    "Voce e a CABECA de uma investigacao de transparencia publica municipal "
    "(Goias, portais NucleoGov). Recebeu um caso em linguagem natural e deve "
    "decompo-lo em SUBTAREFAS FECHADAS -- cada uma cobrindo 1 municipio + 1 "
    "objetivo especifico (ex.: 'contratos e dispensas do CNPJ X em Senador "
    "Canedo', 'folha do servidor Y em jun/2024 em Trindade', 'baixar os "
    "anexos do contrato encontrado'). Va so pelos municipios listados no "
    "caso. Se o caso mencionar um periodo (ano ou intervalo de anos), repita "
    "esse periodo explicitamente em CADA instrucao -- o sistema tambem filtra "
    "o periodo automaticamente, mas a instrucao clara ajuda o worker a nao "
    "gastar chamadas em anos fora do pedido. A instrucao de cada subtarefa "
    "deve ser clara o bastante para o worker (um modelo mais simples com "
    "acesso a tools de busca/download) executar sem ambiguidade. Chame "
    "'definir_plano' com a lista."
)

_ANO_RE = re.compile(r"(?:19|20)\d{2}")


def _extrair_periodo(descricao: str) -> tuple[int, int] | None:
    """F7 (correcao estrutural, nao depende do worker/cabeca obedecer o
    prompt): varre o texto livre do caso por anos de 4 digitos (19xx/20xx) e
    devolve (ano_min, ano_max). Sem nenhum ano mencionado, devolve None (sem
    filtro de periodo -- nem todo caso tem um)."""
    anos = [int(m.group(0)) for m in _ANO_RE.finditer(descricao)]
    if not anos:
        return None
    return min(anos), max(anos)

_DEFINIR_PLANO_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "definir_plano",
        "description": "Decompoe o caso em subtarefas fechadas (1 objetivo/municipio cada).",
        "parameters": {
            "type": "object",
            "properties": {
                "subtarefas": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "municipio": {"type": "string"},
                            "descricao": {"type": "string", "description": "Resumo curto (para o relatorio/lacunas)."},
                            "instrucao": {
                                "type": "string",
                                "description": "Instrucao completa para o worker executar com as tools.",
                            },
                        },
                        "required": ["municipio", "descricao", "instrucao"],
                    },
                },
            },
            "required": ["subtarefas"],
        },
    },
}


def _prompt_caso(caso: dict[str, Any], descricao: str) -> str:
    return json.dumps(
        {
            "descricao_investigacao": descricao,
            "titulo": caso["titulo"],
            "tipo": caso["tipo"],
            "municipios": caso["municipios"],
            "alvos": caso["alvos"],
        },
        ensure_ascii=False,
    )


async def planejar(
    cliente: OpenRouterClient,
    modelo: str,
    caso: dict[str, Any],
    descricao: str,
    max_subtarefas: int,
) -> list[dict[str, Any]]:
    mensagens = [
        {"role": "system", "content": _SYSTEM_PLANEJAMENTO},
        {"role": "user", "content": _prompt_caso(caso, descricao)},
    ]
    msg = await cliente.chat(
        modelo,
        mensagens,
        tools=[_DEFINIR_PLANO_TOOL],
        tool_choice={"type": "function", "function": {"name": "definir_plano"}},
    )
    tool_calls = msg.get("tool_calls") or []
    if not tool_calls:
        raise SemPlano("A cabeca nao chamou 'definir_plano' -- resposta sem plano de subtarefas.")
    try:
        args = json.loads(tool_calls[0]["function"]["arguments"] or "{}")
    except json.JSONDecodeError as exc:
        registrar_tool_call(
            caso["id"], "planejamento", "definir_plano", {}, f"JSON invalido: {exc}", True,
            cliente.custo.tokens_total, cliente.custo.custo_usd,
        )
        raise SemPlano(f"'definir_plano' veio com argumentos invalidos (JSON): {exc}") from exc
    brutas = args.get("subtarefas") or []
    if not brutas:
        registrar_tool_call(
            caso["id"], "planejamento", "definir_plano", args, "sem subtarefas", True,
            cliente.custo.tokens_total, cliente.custo.custo_usd,
        )
        raise SemPlano("A cabeca chamou 'definir_plano' sem nenhuma subtarefa.")
    if len(brutas) > max_subtarefas:
        logger.warning("Plano com %d subtarefas excede o teto (%d); truncando.", len(brutas), max_subtarefas)
    periodo = _extrair_periodo(descricao)
    subtarefas = []
    for i, st in enumerate(brutas[:max_subtarefas], start=1):
        instrucao = st.get("instrucao") or st.get("descricao", "")
        if periodo is not None:
            nota = (
                f"Periodo desta investigacao: {periodo[0]}."
                if periodo[0] == periodo[1]
                else f"Periodo desta investigacao: {periodo[0]} a {periodo[1]}."
            )
            instrucao = f"{instrucao}\n\n{nota} Ignore/nao busque registros fora desse periodo."
        subtarefas.append(
            {
                "id": f"st_{i:03d}",
                "municipio": st.get("municipio", ""),
                "descricao": st.get("descricao") or st.get("instrucao", ""),
                "instrucao": instrucao,
                "periodo": list(periodo) if periodo is not None else None,
            }
        )
    registrar_tool_call(
        caso["id"], "planejamento", "definir_plano", args, f"{len(subtarefas)} subtarefa(s) definida(s)", False,
        cliente.custo.tokens_total, cliente.custo.custo_usd,
    )
    return subtarefas


# --------------------------------------------------------------------------- #
# Validacao contra o manifesto (deterministica -- §6.2 #3/#5) + reexecucao
# --------------------------------------------------------------------------- #


def _validar_evidencias(caso_id: str, resultado: ResultadoSubtarefa) -> tuple[bool, str | None]:
    """Confere que TODA `evidencia_id` que o worker afirmou coletar existe de
    fato no manifesto do caso -- checagem contra o arquivo, nao "confianca"
    no que o modelo disse."""
    if not resultado.sucesso:
        return False, resultado.motivo_falha or "worker reportou falha na subtarefa"
    if not resultado.evidencia_ids:
        # Sucesso sem evidencia e legitimo (ex.: busca que nao achou nada,
        # ou achou item mas ainda nao baixou anexo) -- so rejeita invencao.
        return True, None
    ids_manifesto = {e["evidencia_id"] for e in evidencia.ler_manifesto(caso_id)}
    faltando = [eid for eid in resultado.evidencia_ids if eid not in ids_manifesto]
    if faltando:
        return False, f"evidencia_id(s) sem lastro no manifesto do caso: {faltando}"
    return True, None


async def _executar_com_reexecucao(
    cliente: OpenRouterClient,
    modelo_worker: str,
    subtarefa: dict[str, Any],
    caso_id: str,
    max_iter_worker: int,
    custo: CustoAcumulado,
    teto_tokens: int | None,
    teto_tempo_s: int | None,
    inicio: float,
) -> ResultadoSubtarefa | Lacuna:
    """Roda a subtarefa; se o resultado falhar validacao, reexecuta 1 vez
    (guardrail §6.2 #3). Falhou 2x -> Lacuna explicita."""
    motivo: str | None = None
    for tentativa in range(2):
        if teto_tokens and custo.tokens_total >= teto_tokens:
            return Lacuna(subtarefa["id"], subtarefa["descricao"], "teto de tokens da investigacao atingido")
        if teto_tempo_s and (time.monotonic() - inicio) >= teto_tempo_s:
            return Lacuna(subtarefa["id"], subtarefa["descricao"], "teto de tempo da investigacao atingido")
        resultado = await executar_subtarefa(cliente, modelo_worker, subtarefa, caso_id, max_iter_worker)
        ok, motivo = _validar_evidencias(caso_id, resultado)
        if ok:
            return resultado
        logger.info("Subtarefa %s tentativa %d rejeitada: %s", subtarefa["id"], tentativa + 1, motivo)
    return Lacuna(subtarefa["id"], subtarefa["descricao"], motivo or "falhou 2x sem lastro")


# --------------------------------------------------------------------------- #
# Redacao do relatorio final (mesmo template do P5, §6.3)
# --------------------------------------------------------------------------- #

_SHA_RE = re.compile(r"`([0-9a-fA-F]{8,64})`")
# Token numerico "cru": digitos com pontuacao interna (R$ 3.750.000, CNPJ
# 45.160.810/0001-43, data 14/07/2026, contrato 0343/26, contagem simples) --
# usado pelo guardrail F2 (§6.2 #5) para conferir CADA numero da sintese
# contra o dado estruturado real, nao so os sha256 (ver `_saneiar_sintese`).
_NUM_TOKEN_RE = re.compile(r"\d[\d.,/-]*\d|\d")

_SISTEMA_REDACAO = (
    "Voce e a CABECA de uma investigacao de transparencia publica. Escreva "
    "APENAS o paragrafo de SINTESE do relatorio (2-4 frases, objetivo, com "
    "numeros), a partir EXCLUSIVAMENTE do resumo de achados fornecido. NUNCA "
    "cite numero, valor, data ou sha256 que nao esteja no texto fornecido; "
    "qualquer afirmacao sem lastro direto nos achados deve vir marcada "
    "literalmente '[não verificado]'. Responda so o paragrafo, sem titulo."
)


def _fonte_estruturada(caso: dict[str, Any], caso_id: str) -> str:
    """Concatena TODO valor estruturado real do caso (alvos + campos dos
    itens persistidos + contagens) -- e contra ISSO que qualquer numero
    citado na sintese e conferido (guardrail F2/§6.2 #5: contagens, valores
    e periodos nao podem depender so do texto livre do resumo do worker)."""
    partes: list[str] = [str(v) for v in (caso.get("alvos") or {}).values()]
    itens = caso.get("itens") or []
    por_secao: dict[str, int] = {}
    for item in itens:
        por_secao[item.get("secao", "")] = por_secao.get(item.get("secao", ""), 0) + 1
        for campo in ("titulo", "documento", "valor", "data"):
            if item.get(campo):
                partes.append(str(item[campo]))
    partes.append(str(len(itens)))
    partes.append(str(len(evidencia.ler_manifesto(caso_id))))
    partes.extend(str(v) for v in por_secao.values())
    return " ".join(partes)


def _saneiar_sintese(texto: str, caso_id: str, caso: dict[str, Any]) -> str:
    """Guardrail F2 (§6.2 #5): a sintese so pode citar (a) sha256 reais do
    manifesto e (b) contagens/valores/datas que aparecem, verbatim, nos dados
    ESTRUTURADOS do caso (`_fonte_estruturada`) -- nunca so no texto livre do
    `resumo` do worker. Qualquer numero sem essa correspondencia exata vira
    '[não verificado]': erra para o lado conservador (numero legitimo com
    formatacao diferente tambem e marcado) em vez de arriscar deixar passar
    um numero inventado -- mesma regra anti-alucinacao do projeto."""
    hashes_reais = {e.get("sha256", "") for e in evidencia.ler_manifesto(caso_id)}

    def _trocar_hash(m: re.Match[str]) -> str:
        return m.group(0) if m.group(1) in hashes_reais else "[não verificado]"

    texto = _SHA_RE.sub(_trocar_hash, texto)

    fonte = _fonte_estruturada(caso, caso_id)

    def _trocar_num(m: re.Match[str]) -> str:
        token = m.group(0)
        return token if token in fonte else "[não verificado]"

    # Protege os sha256 ja validados (entre crases) da varredura numerica --
    # so sanitiza numeros no texto corrido da sintese.
    partes = re.split(r"(`[0-9a-fA-F]{8,64}`)", texto)
    return "".join(p if p.startswith("`") else _NUM_TOKEN_RE.sub(_trocar_num, p) for p in partes)


async def _sintese(cliente: OpenRouterClient, modelo: str, caso: dict[str, Any], resultado: ResultadoInvestigacao) -> str:
    contexto = {
        "titulo": caso["titulo"],
        "tipo": caso["tipo"],
        "municipios": caso["municipios"],
        "alvos": caso["alvos"],
        "total_itens": len(caso.get("itens") or []),
        "total_evidencias": len(evidencia.ler_manifesto(caso["id"])),
        "subtarefas_concluidas": [r.resumo for r in resultado.subtarefas_executadas],
        "lacunas": [lac.descricao for lac in resultado.lacunas],
    }
    mensagens = [
        {"role": "system", "content": _SISTEMA_REDACAO},
        {"role": "user", "content": json.dumps(contexto, ensure_ascii=False)},
    ]
    try:
        msg = await cliente.chat(modelo, mensagens, temperature=0.3)
    except OpenRouterError as exc:
        return f"[não verificado] Sintese nao pode ser gerada (falha OpenRouter: {exc})."
    texto = (msg.get("content") or "").strip()
    return texto or "[não verificado] A cabeca nao produziu texto de sintese."


def _secao_regex(titulo: str) -> re.Pattern[str]:
    return re.compile(rf"(## {re.escape(titulo)}\n)(.*?)(?=\n## |\Z)", re.DOTALL)


def _substituir_secao(md: str, titulo: str, novo_conteudo: str) -> str:
    return _secao_regex(titulo).sub(lambda m: m.group(1) + novo_conteudo.strip() + "\n", md, count=1)


def _acrescentar_secao(md: str, titulo: str, conteudo_extra: str) -> str:
    def _rep(m: re.Match[str]) -> str:
        existente = m.group(2).rstrip("\n")
        return m.group(1) + existente + "\n" + conteudo_extra.strip() + "\n"

    return _secao_regex(titulo).sub(_rep, md, count=1)


async def redigir_relatorio(
    cliente: OpenRouterClient, modelo: str, caso_id: str, resultado: ResultadoInvestigacao
) -> str:
    caso = casos.obter_caso(caso_id)
    if caso is None:
        raise ValueError(f"Caso '{caso_id}' nao encontrado.")

    md = relatorio.gerar_relatorio_markdown(caso_id)

    sintese = _saneiar_sintese(await _sintese(cliente, modelo, caso, resultado), caso_id, caso)
    md = _substituir_secao(md, "Síntese", sintese)

    if resultado.lacunas:
        extra = "\n".join(
            f"- **{lac.descricao}** ({lac.subtarefa_id}): {lac.motivo} [não verificado]" for lac in resultado.lacunas
        )
        md = _acrescentar_secao(md, "Lacunas e ressalvas", extra)

    custo_txt = f"{resultado.custo.tokens_total} tokens"
    if resultado.custo.custo_usd is not None:
        custo_txt += f", US$ {resultado.custo.custo_usd:.4f}"
    else:
        custo_txt += " (custo em USD nao informado pelo provedor)"
    custo_txt += f" em {resultado.custo.chamadas} chamada(s) ao OpenRouter."
    if resultado.teto_atingido:
        custo_txt += " **Teto de custo/tempo atingido — entrega parcial.**"
    md = md.rstrip("\n") + f"\n\n---\nCusto da investigação: {custo_txt}\n"
    return md


# --------------------------------------------------------------------------- #
# Entrada publica
# --------------------------------------------------------------------------- #


async def investigar(
    caso_id: str,
    descricao: str,
    *,
    api_key: str,
    base_url: str,
    modelo_cabeca: str,
    modelo_worker: str,
    max_subtarefas: int,
    max_iter_worker: int,
    teto_tokens: int | None = None,
    teto_tempo_s: int | None = None,
    db: Any = None,
    cliente_http: httpx.AsyncClient | None = None,
) -> ResultadoInvestigacao:
    """Orquestra UMA investigacao completa: planeja -> despacha subtarefas ao
    worker (com reexecucao/lacuna) -> redige o relatorio -> grava em disco no
    dossie do caso (`data/casos/<id>/relatorio.md`)."""
    caso = casos.obter_caso(caso_id, db=db)
    if caso is None:
        raise ValueError(f"Caso '{caso_id}' nao encontrado.")

    custo = CustoAcumulado()
    cliente = OpenRouterClient(api_key, base_url, custo, client=cliente_http)
    inicio = time.monotonic()
    resultado = ResultadoInvestigacao(caso_id=caso_id, custo=custo)
    try:
        try:
            subtarefas = await planejar(cliente, modelo_cabeca, caso, descricao, max_subtarefas)
        except (OpenRouterError, SemPlano) as exc:
            resultado.lacunas.append(Lacuna("planejamento", "Planejamento da investigacao", str(exc)))
            subtarefas = []

        for st in subtarefas:
            item = await _executar_com_reexecucao(
                cliente, modelo_worker, st, caso_id, max_iter_worker, custo, teto_tokens, teto_tempo_s, inicio
            )
            if isinstance(item, Lacuna):
                resultado.lacunas.append(item)
            else:
                resultado.subtarefas_executadas.append(item)

        if (teto_tokens and custo.tokens_total >= teto_tokens) or (
            teto_tempo_s and (time.monotonic() - inicio) >= teto_tempo_s
        ):
            resultado.teto_atingido = True

        relatorio_md = await redigir_relatorio(cliente, modelo_cabeca, caso_id, resultado)
        resultado.relatorio_md = relatorio_md
        caminho = relatorio.caminho_relatorio(caso_id)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(relatorio_md, encoding="utf-8")
        resultado.relatorio_path = str(caminho)
    finally:
        await cliente.aclose()
    return resultado


__all__ = ["investigar", "planejar", "redigir_relatorio", "ResultadoInvestigacao", "Lacuna", "SemPlano"]
