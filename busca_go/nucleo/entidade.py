"""Busca por ENTIDADE nos portais NucleoGov (contratos/licitacoes/dispensas + folha).

O usuario escolhe UM municipio e digita num campo unico um CPF, CNPJ, nome ou
termo. Este modulo:

1. DETECTA o tipo da entrada (`detectar_tipo`): 11 digitos = CPF, 14 = CNPJ,
   senao termo livre.
2. DIRIGE o portal via httpx reproduzindo o `POST /api multi_request`
   (`_multi`) — decisao arquitetural: o portal responde esse POST em JSON
   (`{"k1":{"total":N,"dados":[...]}}`) com apenas um UA de desktop, sem CSRF;
   e muito mais rapido/robusto que dirigir o browser (Playwright fica reservado
   ao `/api/buscar` legado de navegacao por secao).
3. AGREGA (`pesquisar`): consulta as secoes aplicaveis, agrupa por secao, marca
   aditivos dentro de contratos e devolve um payload unico com avisos.

Estrategia server-side-primeiro-com-fallback (ver `_coletar`):
- CNPJ/CPF: o indice de busca dos portais NAO cobre documento (comprovado ao
  vivo: um CNPJ existente retorna total=0). Por isso documento SEMPRE varre as
  paginas (`limit` com count=50) e filtra localmente pelo documento normalizado
  presente em QUALQUER campo da linha (o nome do campo varia por portal:
  `contratado_documento`, `fornecedor_cpfcnpj`, `cnpj_cpf`).
- Termo/nome: TENTA o campo de busca do portal (`txtbusca`/`busca`) e VALIDA o
  efeito — a contagem caiu E ao menos um item retornado contem de fato o termo.
  So entao confia no server-side; senao (ou se o server-side zerou, caso
  ambiguo) cai para a varredura + filtro local. Nao ha lista hardcoded de
  "secoes com bug": a decisao sai da validacao do efeito.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import re
import unicodedata
from typing import Any, Callable, Iterable

import httpx

from ..municipios import Municipio, get as get_mun
from . import capacidades, centi
from .routes import SecaoIndisponivel

# UA de desktop obrigatorio: portais NucleoGov (Rio Verde, Trindade) respondem
# 403 (WAF) a UA com "HeadlessChrome". Com este UA, o POST /api retorna 200.
_UA_CHROME = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

# Paginacao do portal: maximo 50 registros por chamada (nao existe "ver todos").
_PAGE = 50
# Teto de paginas por secao numa varredura (25 * 50 = 1250 registros). Portais
# grandes (ex.: contratos de Cristalina ~28k) sao truncados COM aviso explicito.
_MAX_PAGINAS = 25
# Teto de itens coletados de um resultado server-side ja filtrado.
_MAX_ITENS_SERVER = 500


class PortalError(RuntimeError):
    """O portal do municipio recusou/quebrou a requisicao (nao e vazio legitimo)."""


# Retry de requisicao: erros transitorios (timeout/conexao) podem se resolver
# numa nova tentativa; um soluco pontual nao deve derrubar a busca inteira.
_TENTATIVAS_RETRY = 3
_BACKOFF_SEGUNDOS = 0.5

# Retry para HTTP 202 -- bloqueio SUAVE do WAF do NucleoGov (nao e erro, mas
# tambem nao e sucesso: comprovado na aceitacao final, F3 -- 4 jobs de folha +
# 18 tentativas via `pesquisar` bateram em 202 repetido enquanto chamadas
# isoladas passavam segundos depois). Mecanismo PROPRIO, separado do retry de
# timeout/conexao acima: backoff educado e LIMITADO (portal publico, nada
# agressivo), honra `Retry-After` quando o portal manda. Configuravel via env
# para permitir ajuste sem redeploy caso o WAF mude de comportamento.
_TENTATIVAS_202 = int(os.getenv("BUSCA_GO_202_TENTATIVAS", "4"))
_BACKOFF_202_MIN_S = float(os.getenv("BUSCA_GO_202_BACKOFF_MIN_S", "2.0"))
_BACKOFF_202_MAX_S = float(os.getenv("BUSCA_GO_202_BACKOFF_MAX_S", "15.0"))

# Traducao amigavel do nome da excecao httpx quando str(exc) vem vazio (comum
# em timeouts, onde a mensagem original nao carrega texto nenhum).
_MSGS_AMIGAVEIS = {
    "ConnectTimeout": "tempo de conexao esgotado",
    "ReadTimeout": "tempo de resposta esgotado",
    "WriteTimeout": "tempo de envio esgotado",
    "PoolTimeout": "tempo de espera por conexao disponivel esgotado",
    "ConnectError": "falha ao conectar ao portal",
}


def _msg_falha_rede(exc: BaseException) -> str:
    """Mensagem de erro de rede que NUNCA termina truncada em ':'.

    `str(exc)` vem vazio para varios erros do httpx (ex.: ReadTimeout) — nesse
    caso usamos o nome da classe traduzido para pt-BR em vez de deixar a
    mensagem cortada.
    """
    detalhe = str(exc).strip()
    if not detalhe:
        nome = type(exc).__name__
        amigavel = _MSGS_AMIGAVEIS.get(nome, nome)
        detalhe = f"{amigavel} ({nome})"
    return f"Falha de rede ao consultar o portal: {detalhe}"


# --------------------------------------------------------------------------- #
# Deteccao de entidade
# --------------------------------------------------------------------------- #

_SO_DOC = re.compile(r"^[\d.\-/\s]+$")


def detectar_tipo(entrada: str) -> tuple[str, str]:
    """Classifica a entrada do usuario.

    Regras (decisao do orquestrador): normaliza tirando pontuacao; se sobrar
    SOMENTE digitos, 11 = cpf e 14 = cnpj. Qualquer coisa com letras, ou com
    contagem de digitos diferente, e termo livre.

    Returns:
        (tipo, needle) onde tipo in {"cpf","cnpj","termo"}. Para cpf/cnpj o
        needle e so os digitos; para termo, o texto original sem espacos nas
        pontas.
    """
    bruto = (entrada or "").strip()
    if bruto and _SO_DOC.match(bruto):
        digitos = re.sub(r"\D", "", bruto)
        if len(digitos) == 11:
            return "cpf", digitos
        if len(digitos) == 14:
            return "cnpj", digitos
    return "termo", bruto


# --------------------------------------------------------------------------- #
# Normalizacao / matching local
# --------------------------------------------------------------------------- #


def _so_digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto or "")


def _fold(texto: str) -> str:
    """minusculas sem acento, para comparacao de termo tolerante."""
    nfkd = unicodedata.normalize("NFKD", texto or "")
    sem_acento = "".join(c for c in nfkd if not unicodedata.combining(c))
    return sem_acento.lower()


def _campos_texto(item: dict[str, Any]) -> Iterable[str]:
    """Valores escalares (str/num) do item, para busca campo-a-campo."""
    for v in item.values():
        if isinstance(v, str):
            yield v
        elif isinstance(v, (int, float)):
            yield str(v)


def _match_documento(item: dict[str, Any], needle_digitos: str) -> bool:
    """True se ALGUM campo do item contem o documento (comparando so digitos).

    Compara campo-a-campo (nao concatena tudo) para nao casar digitos que se
    juntam por acaso entre colunas vizinhas.
    """
    for valor in _campos_texto(item):
        if needle_digitos in _so_digitos(valor):
            return True
    return False


def _match_termo(item: dict[str, Any], needle: str) -> bool:
    """True se TODOS os tokens do termo aparecem no texto do item (sem acento)."""
    alvo = _fold(" ".join(_campos_texto(item)))
    tokens = [t for t in _fold(needle).split() if t]
    return bool(tokens) and all(t in alvo for t in tokens)


# --------------------------------------------------------------------------- #
# Aditivos + normalizacao de item de saida
# --------------------------------------------------------------------------- #

_ADITIVO_KEYS = ("aditivos", "aditivo", "tipo_aditivo", "num_adt", "adt")


def _tem_aditivo(item: dict[str, Any]) -> bool:
    """Best-effort: a linha de contrato carrega aditivo/aditamento?

    Aditamentos nao tem secao propria (confirmado na auditoria) — aparecem como
    campo dentro da linha de contratos. Aqui sinalizamos a presenca; nao ha
    busca dedicada.
    """
    for k in _ADITIVO_KEYS:
        v = item.get(k)
        if isinstance(v, list):
            if v:
                return True
        elif isinstance(v, (int, float)):
            if v > 0:
                return True
        elif isinstance(v, str):
            s = v.strip()
            if s and s not in ("0", "0.00", "n", "N", "nao", "null", "None"):
                return True
    return False


_F_NOME = (
    "nome", "contratado_nome", "nome_contratado", "razao_social", "fornecedor",
    "credor", "fornecedor_nome",
)
_F_DOC = ("cnpj_cpf", "contratado_documento", "fornecedor_cpfcnpj", "cpf_cnpj", "documento", "cnpj", "cpf")
_F_DESC = ("descricao", "objeto", "ementa")
_F_NUM = ("numero_contrato", "numero", "label", "numero_processo", "numero_detalhado")
_F_VALOR = ("valor", "valor_total", "valor_estimado", "valor_contrato", "total_liquido")
_F_DATA = ("data_publicacao", "data", "data_edital", "data_firmatura", "data_assinatura", "data_abertura")

# Identificadores do registro para o passo LAZY de anexos (ver nucleo/anexos.py):
# o download precisa localizar o registro de novo (modo A: listarAnexos com
# id/numero/anobase; modo B: reobter o registro fresco por numero). Estes campos
# sao PRESERVADOS na serializacao para nao perder o identificador entre a busca e
# o download.
_F_REG_ID = ("id", "contrato_id", "licitacao_id", "contrato", "licitacao")
_F_REG_ANO = ("anobase", "ano", "contrato_ano", "ano_lic")


def _pick(item: dict[str, Any], chaves: tuple[str, ...]) -> str:
    for k in chaves:
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, (int, float)) and str(v).strip():
            return str(v)
    return ""


# Campos de DIFERENCIACAO de servidor (folha). Como o CPF vem mascarado, a UI
# distingue homonimos pela MATRICULA (chave unica) + cargo/lotacao/referencia/
# tipo de folha. Esses campos NUNCA sao descartados na serializacao da folha.
_F_MATRICULA = ("matricula", "registro", "codigo")
_F_CARGO = ("cargo", "funcao", "cargo_funcao")
_F_LOTACAO = ("lotacao", "lotacao_nome", "setor", "unidade", "departamento")
_F_ORGAO = ("orgao", "orgao_nome")
_F_VINCULO = ("vinculo", "tipo_vinculo", "tipoDeVinculo")
_F_REFERENCIA = ("referencia", "ref", "nivel")
_F_TIPO_FOLHA = ("tipo_folha", "tipo", "folha")
_F_PROVENTOS = ("total_proventos", "proventos", "bruto")
_F_DESCONTOS = ("total_desconto", "total_descontos", "descontos")
_F_LIQUIDO = ("total_liquido", "liquido", "valor", "totalLiquido")


def _normalizar_item(item: dict[str, Any], secao: str) -> dict[str, Any]:
    """Item de portal -> item de saida com campos comuns + `raw` original.

    Os nomes de campo variam por portal; escolhemos o primeiro presente de cada
    familia e sempre preservamos `raw` para a UI/depuracao. A folha tem
    serializacao propria (`_normalizar_folha`) que preserva os campos de
    diferenciacao de servidor (matricula, cargo, lotacao...).
    """
    if secao == "folha":
        return _normalizar_folha(item)
    descricao = _pick(item, _F_DESC)
    return {
        "titulo": _pick(item, _F_NUM) or descricao,
        "descricao": descricao,
        "fornecedor": _pick(item, _F_NOME),
        "documento": _pick(item, _F_DOC),
        "valor": _pick(item, _F_VALOR),
        "data": _pick(item, _F_DATA),
        "tem_aditivo": _tem_aditivo(item) if secao == "contratos" else False,
        # Identificadores para o passo lazy de anexos (nao descartar).
        "ref_registro": {
            "id": _pick(item, _F_REG_ID),
            "numero": _pick(item, _F_NUM),
            "ano": _pick(item, _F_REG_ANO),
        },
        # Indicador BARATO: True so quando o array `anexos` ja veio populado no
        # item (modo B "embutido_url_assinada"). Modo A nao expoe isso na
        # listagem -> None (a existencia de anexo so se sabe sob demanda).
        "tem_anexos": _tem_anexos_embutido(item),
        "raw": item,
    }


def _tem_anexos_embutido(item: dict[str, Any]) -> bool | None:
    """True se o item ja traz `anexos` como lista NAO vazia (modo B populado).

    Em Senador Canedo (modo A) o campo `anexos` do item e uma URL string
    (armadilha, retorna 401) — nao uma lista; entao la isto resulta None
    ("sob demanda"), nunca um falso positivo.
    """
    anx = item.get("anexos")
    if isinstance(anx, list):
        return len(anx) > 0
    return None


def _normalizar_folha(item: dict[str, Any]) -> dict[str, Any]:
    """Linha de folha -> item com os campos de diferenciacao de servidor.

    CPF esta suspenso (o portal o mascara), entao a distincao de HOMONIMOS sai
    da MATRICULA (chave unica) + cargo/lotacao/orgao/referencia/tipo de folha.
    Estes campos vem explicitos aqui (nao so em `raw`) para a UI diferenciar
    pessoas de mesmo nome sem reparsear.
    """
    return {
        "matricula": _pick(item, _F_MATRICULA),
        "nome": _pick(item, _F_NOME),
        "cargo": _pick(item, _F_CARGO),
        "lotacao": _pick(item, _F_LOTACAO),
        "orgao": _pick(item, _F_ORGAO),
        "vinculo": _pick(item, _F_VINCULO),
        "referencia": _pick(item, _F_REFERENCIA),
        "tipo_folha": _pick(item, _F_TIPO_FOLHA),
        "ano": _pick(item, ("ano",)),
        "mes": _pick(item, ("mes",)),
        "proventos": _pick(item, _F_PROVENTOS),
        "descontos": _pick(item, _F_DESCONTOS),
        "liquido": _pick(item, _F_LIQUIDO),
        "cpf_mascarado": _pick(item, ("cpf",)),
        "raw": item,
    }


def _agrupar_por_matricula(itens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Agrupa linhas de folha por MATRICULA (um servidor -> suas folhas no periodo).

    Resolve homonimos: cada servidor vira um bloco com seus dados de
    identificacao e a lista de folhas (uma por mes/tipo). Linhas sem matricula
    caem num grupo proprio por nome (fallback), sinalizado com matricula "".
    """
    ordem: list[str] = []
    grupos: dict[str, dict[str, Any]] = {}
    for it in itens:
        chave = it.get("matricula") or f"nome:{_fold(it.get('nome', ''))}"
        g = grupos.get(chave)
        if g is None:
            g = {
                "matricula": it.get("matricula", ""),
                "nome": it.get("nome", ""),
                "cargo": it.get("cargo", ""),
                "lotacao": it.get("lotacao", ""),
                "orgao": it.get("orgao", ""),
                "folhas": [],
            }
            grupos[chave] = g
            ordem.append(chave)
        g["folhas"].append(it)
    return [grupos[k] for k in ordem]


# --------------------------------------------------------------------------- #
# Driver httpx do POST multi_request
# --------------------------------------------------------------------------- #


def _retry_after_segundos(resp: httpx.Response) -> float | None:
    """Le `Retry-After` da resposta em segundos, se presente e numerico.

    O cabecalho HTTP tambem aceita formato de data (RFC 7231); esse formato
    nao e tratado aqui -- cai no backoff padrao, que ja e seguro.
    """
    valor = resp.headers.get("Retry-After")
    if not valor:
        return None
    try:
        return float(valor)
    except ValueError:
        return None


def _espera_202(tentativa: int, retry_after: float | None) -> float:
    """Tempo de espera antes de reentrar apos um 202 (bloqueio suave do WAF).

    Com `Retry-After`, honra o portal (limitado a `_BACKOFF_202_MAX_S` para
    nao esperar tempo desproporcional). Sem ele, backoff crescente com jitter
    dentro de `[_BACKOFF_202_MIN_S, _BACKOFF_202_MAX_S]` -- educado com um
    portal publico, nunca agressivo.
    """
    if retry_after is not None:
        return max(_BACKOFF_202_MIN_S, min(retry_after, _BACKOFF_202_MAX_S))
    base = _BACKOFF_202_MIN_S * (tentativa + 1)
    jitter = random.uniform(0, _BACKOFF_202_MIN_S)
    return min(base + jitter, _BACKOFF_202_MAX_S)


async def _post_com_retry(
    client: httpx.AsyncClient, url: str, corpo: dict[str, Any]
) -> httpx.Response:
    """POST com retry para erros transitorios (timeout/conexao) e para HTTP 202.

    Dois mecanismos de retry independentes:
    - timeout/conexao: ate `_TENTATIVAS_RETRY` tentativas, backoff curto fixo
      (erro de rede, nao e bloqueio de WAF).
    - HTTP 202 (bloqueio SUAVE do WAF, ver F3 da aceitacao final): ate
      `_TENTATIVAS_202` tentativas adicionais por resposta 202, honrando
      `Retry-After` quando presente. 202 persistente apos esgotar vira
      PortalError com mensagem especifica (nao a generica de falha de rede).

    Erros de rede que NAO sao timeout/conexao (ex.: erro de protocolo)
    propagam direto, sem retry, para `_multi` decidir.

    Raises:
        PortalError: timeout/conexao esgotados, OU 202 persistente apos
            esgotar `_TENTATIVAS_202`.
        httpx.HTTPError: erro de rede que nao e timeout/transporte (sem retry).
    """
    ultimo_exc: BaseException | None = None
    for tentativa in range(_TENTATIVAS_RETRY):
        try:
            resp = await client.post(url, data=corpo)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            ultimo_exc = exc
            if tentativa < _TENTATIVAS_RETRY - 1:
                await asyncio.sleep(_BACKOFF_SEGUNDOS * (tentativa + 1))
            continue
        if resp.status_code != 202:
            return resp
        for tentativa_202 in range(_TENTATIVAS_202):
            await asyncio.sleep(_espera_202(tentativa_202, _retry_after_segundos(resp)))
            resp = await client.post(url, data=corpo)
            if resp.status_code != 202:
                return resp
        raise PortalError("O portal recusou temporariamente — tente novamente.")
    raise PortalError(_msg_falha_rede(ultimo_exc)) from ultimo_exc


async def _multi(
    client: httpx.AsyncClient,
    url_base: str,
    acao: str,
    params: dict[str, Any],
    offset: int,
    count: int,
    modo_api: str = "padrao",
) -> dict[str, Any]:
    """Reproduz o POST /api multi_request e devolve o bloco k1 normalizado.

    Args:
        modo_api: "padrao" (todas as cidades ate 2026-07-07) envia
            `limit="<offset>, <count>"` e le `k1.dados` na resposta.
            "megasoft" (folha de Caldazinha, sabor `_mg`, ver
            `capacidades.Capacidade.modo_api`) envia `pagina`/
            `tamanhoDaPagina` (paginacao por numero de pagina, `offset`
            convertido internamente) e le `k1.registros`.

    Returns:
        {"total": int, "dados": list[dict]} — total do portal e a pagina de
        dados (chave sempre normalizada para "dados", independente do nome
        real na resposta do portal). Uma resposta inesperada (ex.: k1 vindo
        como lista vazia, sinal de acao invalida) vira {"total":0,"dados":[]},
        nunca excecao — para nao confundir "acao vazia" com "portal fora do ar".

    Raises:
        PortalError: status HTTP != 200, corpo nao-JSON, ou falha de rede
            persistente apos as tentativas de retry (portal recusou/caiu).
    """
    if modo_api == "megasoft":
        k1_req = {"acao": acao, "pagina": offset // count + 1, "tamanhoDaPagina": count, **params}
        chave_dados = "registros"
    else:
        k1_req = {"acao": acao, "limit": f"{offset}, {count}", **params}
        chave_dados = "dados"
    corpo = {
        "multi_request": "true",
        "params": json.dumps({"k1": k1_req}),
    }
    try:
        resp = await _post_com_retry(client, f"{url_base}/api", corpo)
    except httpx.HTTPError as exc:
        raise PortalError(_msg_falha_rede(exc)) from exc
    if resp.status_code != 200:
        raise PortalError(f"O portal recusou o acesso (HTTP {resp.status_code}).")
    try:
        # r.content e ASCII com escapes \uXXXX; json decodifica direto.
        data = json.loads(resp.content)
    except (json.JSONDecodeError, ValueError) as exc:
        raise PortalError(f"Resposta invalida do portal: {exc}") from exc
    k1 = data.get("k1") if isinstance(data, dict) else None
    if not isinstance(k1, dict):
        return {"total": 0, "dados": []}
    dados = k1.get(chave_dados)
    if not isinstance(dados, list):
        dados = []
    total = k1.get("total")
    try:
        total = int(total)
    except (TypeError, ValueError):
        total = len(dados)
    return {"total": total, "dados": dados}


# --------------------------------------------------------------------------- #
# Coleta por secao (server-side-primeiro-com-fallback)
# --------------------------------------------------------------------------- #


async def _varrer_e_filtrar(
    client: httpx.AsyncClient,
    url_base: str,
    cap: capacidades.Capacidade,
    predicado: Callable[[dict[str, Any]], bool],
) -> tuple[list[dict[str, Any]], int, bool]:
    """Pagina `acao_listar` ate o teto e filtra localmente por `predicado`.

    Returns:
        (itens_filtrados, total_portal, truncado).
    """
    itens: list[dict[str, Any]] = []
    total_portal = 0
    offset = 0
    truncado = False
    paginas = 0
    while paginas < _MAX_PAGINAS:
        pg = await _multi(client, url_base, cap.acao_listar, dict(cap.extra), offset, _PAGE)
        if paginas == 0:
            total_portal = pg["total"]
        dados = pg["dados"]
        if not dados:
            break
        itens.extend(it for it in dados if predicado(it))
        paginas += 1
        offset += _PAGE
        if total_portal and offset >= total_portal:
            break
    if total_portal and total_portal > _MAX_PAGINAS * _PAGE:
        truncado = True
    return itens, total_portal, truncado


async def _coletar_termo(
    client: httpx.AsyncClient,
    url_base: str,
    cap: capacidades.Capacidade,
    needle: str,
) -> tuple[str, list[dict[str, Any]], int, bool]:
    """Termo/nome: server-side-primeiro-com-fallback.

    Returns:
        (modo, itens, total_portal, truncado) com modo in {"server","varredura"}.
    """
    if cap.campo_busca and cap.acao_busca:
        params_busca = {cap.campo_busca: needle, **cap.extra}
        primeiro = await _multi(client, url_base, cap.acao_busca, params_busca, 0, _PAGE)
        base = await _multi(client, url_base, cap.acao_listar, dict(cap.extra), 0, 1)
        filtrou = base["total"] == 0 or primeiro["total"] < base["total"]
        casou = any(_match_termo(it, needle) for it in primeiro["dados"])
        # So confia no server-side se filtrou E ha match real E nao zerou (zero
        # e ambiguo entre "vazio legitimo" e "campo ignorado" -> vai pra varredura).
        if filtrou and primeiro["total"] > 0 and casou:
            itens = list(primeiro["dados"])
            offset = _PAGE
            truncado = False
            while offset < primeiro["total"] and len(itens) < _MAX_ITENS_SERVER:
                pg = await _multi(client, url_base, cap.acao_busca, params_busca, offset, _PAGE)
                if not pg["dados"]:
                    break
                itens.extend(pg["dados"])
                offset += _PAGE
            if len(itens) < primeiro["total"]:
                truncado = True
            return "server", itens[:_MAX_ITENS_SERVER], primeiro["total"], truncado
    # Fallback: varre e filtra localmente pelo termo.
    itens, total_portal, truncado = await _varrer_e_filtrar(
        client, url_base, cap, lambda it: _match_termo(it, needle)
    )
    return "varredura", itens, total_portal, truncado


async def _coletar_documento(
    client: httpx.AsyncClient,
    url_base: str,
    cap: capacidades.Capacidade,
    needle_digitos: str,
) -> tuple[str, list[dict[str, Any]], int, bool]:
    """CNPJ/CPF: o indice do portal nao cobre documento -> sempre varre+filtra."""
    itens, total_portal, truncado = await _varrer_e_filtrar(
        client, url_base, cap, lambda it: _match_documento(it, needle_digitos)
    )
    return "varredura", itens, total_portal, truncado


# --------------------------------------------------------------------------- #
# Folha (nome + periodo)
# --------------------------------------------------------------------------- #


async def _grupo_folha(
    client: httpx.AsyncClient,
    mun: Municipio,
    tipo: str,
    needle: str,
    ano: int | None,
    mes: int | None,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Folha por NOME + periodo. CPF/CNPJ na folha estao SUSPENSOS (mascarados)."""
    avisos: list[str] = []
    try:
        cap = capacidades.resolver(mun.slug, "folha")
    except SecaoIndisponivel:
        return None, avisos
    if tipo in ("cpf", "cnpj"):
        avisos.append(
            "Busca de folha por CPF/CNPJ esta suspensa (o portal mascara o CPF do "
            "servidor); informe o NOME para consultar a folha."
        )
        return None, avisos
    if not (cap.campo_busca and cap.acao_busca):
        return None, avisos
    params: dict[str, Any] = {cap.campo_busca: needle, **cap.extra}
    if ano:
        params["ano"] = str(ano)
    if mes:
        params["mes"] = f"{int(mes):02d}"
    if not (ano and mes):
        avisos.append("Folha sem ano/mes: o portal retorna o periodo mais recente disponivel.")
    itens: list[dict[str, Any]] = []
    offset = 0
    total_portal = 0
    truncado = False
    while offset < _MAX_ITENS_SERVER:
        pg = await _multi(client, mun.url_base, cap.acao_busca, params, offset, _PAGE, cap.modo_api)
        if offset == 0:
            total_portal = pg["total"]
        if not pg["dados"]:
            break
        itens.extend(pg["dados"])
        offset += _PAGE
        if total_portal and offset >= total_portal:
            break
    if total_portal and len(itens) < total_portal:
        truncado = True
    itens_norm = [_normalizar_folha(it) for it in itens]
    servidores = _agrupar_por_matricula(itens_norm)
    if len(servidores) > 1:
        avisos.append(
            f"Folha: {len(servidores)} servidores distintos para '{needle}' "
            "(possiveis homonimos) — diferencie por matricula/cargo/lotacao."
        )
    grupo = {
        "secao": "folha",
        "modo": "server",
        "total": len(itens_norm),
        "total_portal": total_portal,
        "truncado": truncado,
        # linhas planas (cada uma com matricula/cargo/lotacao) para a UI...
        "itens": itens_norm,
        # ...e ja agrupadas por servidor (matricula) ao longo dos meses pedidos.
        "servidores": servidores,
    }
    return grupo, avisos


# --------------------------------------------------------------------------- #
# Agregador publico
# --------------------------------------------------------------------------- #


def _novo_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={"User-Agent": _UA_CHROME, "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8"},
        # Portais NucleoGov sao lentos em varreduras grandes; read folgado, mas
        # sem exagerar (a busca total deve ficar sob ~2min mesmo com retries).
        timeout=httpx.Timeout(connect=10.0, read=50.0, write=10.0, pool=10.0),
        follow_redirects=True,
    )


async def pesquisar(
    slug: str,
    q: str,
    ano: int | None = None,
    mes: int | None = None,
    client: httpx.AsyncClient | None = None,
    secoes: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Busca por entidade num municipio: detecta o tipo, agrega por secao.

    Args:
        slug: municipio (ex.: 'senadorcanedo').
        q: entrada unica do usuario (CPF/CNPJ/nome/termo).
        ano, mes: periodo (usado pela folha).
        client: httpx.AsyncClient opcional (injetavel em teste); se None, cria e
            fecha um proprio.
        secoes: restringe quais secoes sao consultadas (subconjunto de
            `capacidades.SECOES_ENTIDADE` + "folha"). None (padrao) mantem o
            comportamento historico: varre todas as secoes documentais
            disponiveis e, por fim, a folha. Use `secoes=["folha"]` (ou o
            atalho `pesquisar_folha`) quando o objetivo e SO folha -- varrer
            contratos/licitacoes/dispensas pelo nome do servidor antes e ruido
            que ainda por cima dispara o WAF contra a propria folha (F4 da
            aceitacao final: `_grupo_folha` direto passou de primeira, a
            varredura completa falhou 18x em 202).

    Returns:
        {
          "tipo": "cpf"|"cnpj"|"termo",
          "termo": <needle>,
          "municipio": {"slug":..., "nome":...},
          "grupos": [{"secao":..., "modo":..., "total":..., "total_portal":...,
                      "truncado":..., "itens":[...]}],
          "avisos": [...]
        }

    Raises:
        KeyError: municipio nao cadastrado.
        PortalError: falha de portal (o endpoint traduz para HTTP 502).
    """
    mun = get_mun(slug)  # KeyError se nao cadastrado
    tipo, needle = detectar_tipo(q)
    if not needle:
        return {
            "tipo": tipo,
            "termo": needle,
            "municipio": {"slug": mun.slug, "nome": mun.nome},
            "grupos": [],
            "avisos": ["Busca vazia: informe um CPF, CNPJ, nome ou termo."],
        }

    disponiveis = set(capacidades.routes.secoes_disponiveis(slug))
    secoes_permitidas = set(secoes) if secoes is not None else None
    avisos: list[str] = []
    grupos: list[dict[str, Any]] = []
    algum_aditivo = False
    secoes_tentadas = 0
    secoes_falharam = 0

    fechar = client is None
    cli = client or _novo_client()
    try:
        for secao in capacidades.SECOES_ENTIDADE:
            if secao not in disponiveis:
                continue
            if secoes_permitidas is not None and secao not in secoes_permitidas:
                continue
            try:
                cap = capacidades.resolver(slug, secao)
            except SecaoIndisponivel:
                continue
            secoes_tentadas += 1
            try:
                if tipo in ("cpf", "cnpj"):
                    modo, itens_raw, total_portal, truncado = await _coletar_documento(
                        cli, mun.url_base, cap, needle
                    )
                else:
                    modo, itens_raw, total_portal, truncado = await _coletar_termo(
                        cli, mun.url_base, cap, needle
                    )
            except PortalError as exc:
                # Uma secao fora do ar nao derruba a busca inteira: registra o
                # aviso e segue para as demais secoes.
                secoes_falharam += 1
                avisos.append(
                    f"Nao foi possivel consultar a secao '{secao}' do portal "
                    f"({exc}); mostrando o restante."
                )
                continue
            itens = [_normalizar_item(it, secao) for it in itens_raw]
            if secao == "contratos" and any(i["tem_aditivo"] for i in itens):
                algum_aditivo = True
            grupos.append(
                {
                    "secao": secao,
                    "modo": modo,
                    "total": len(itens),
                    "total_portal": total_portal,
                    "truncado": truncado,
                    "itens": itens,
                }
            )
            if truncado:
                avisos.append(
                    f"Secao '{secao}' tem mais de {_MAX_PAGINAS * _PAGE} registros no "
                    f"portal ({total_portal}); a varredura foi limitada e pode nao ter "
                    "trazido todos os itens."
                )

        # Folha: por nome + periodo (contratos/licitacoes/dispensas ja cobertos).
        if "folha" in disponiveis and (secoes_permitidas is None or "folha" in secoes_permitidas):
            secoes_tentadas += 1
            try:
                grupo_folha, avisos_folha = await _grupo_folha(cli, mun, tipo, needle, ano, mes)
            except PortalError as exc:
                secoes_falharam += 1
                avisos.append(
                    f"Nao foi possivel consultar a folha do portal ({exc}); "
                    "mostrando o restante."
                )
            else:
                avisos.extend(avisos_folha)
                if grupo_folha is not None:
                    grupos.append(grupo_folha)

        if secoes_tentadas and secoes_falharam == secoes_tentadas:
            # NENHUMA secao respondeu: portal totalmente fora do ar -> 502 real,
            # nao faz sentido devolver 200 sem nenhum dado.
            raise PortalError(
                "Nao foi possivel consultar nenhuma secao do portal apos "
                "as tentativas de retry (portal parece fora do ar)."
            )
    finally:
        if fechar:
            await cli.aclose()

    if algum_aditivo:
        avisos.append(
            "Ha contratos com ADITIVO/aditamento (marcados em 'tem_aditivo'); "
            "aditamentos nao tem secao propria, aparecem dentro do contrato."
        )
    if tipo == "cnpj":
        avisos.append(
            "CNPJ nao e indexado pela busca dos portais; a consulta varre as "
            "paginas e filtra localmente pelo documento."
        )

    return {
        "tipo": tipo,
        "termo": needle,
        "municipio": {"slug": mun.slug, "nome": mun.nome},
        "grupos": grupos,
        "avisos": avisos,
    }


async def pesquisar_folha(
    slug: str,
    q: str,
    ano: int | None = None,
    mes: int | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Atalho de `pesquisar` para o caso de uso "so folha" (F4 da aceitacao final).

    Casos de dano ao erario/folha nao precisam varrer contratos/licitacoes/
    dispensas pelo nome do servidor -- essa varredura e ruido puro para o
    objetivo E dispara o WAF contra a propria folha (comprovado: `_grupo_folha`
    direto persistiu o mes pedido na 1a tentativa, enquanto `pesquisar` com
    varredura completa falhou 18x em 202). Mesmo contrato/retorno de
    `pesquisar`, so que restrito a `secoes=["folha"]`.
    """
    return await pesquisar(slug, q, ano=ano, mes=mes, client=client, secoes=["folha"])


# --------------------------------------------------------------------------- #
# Busca combinada nome+CNPJ (blueprint §3.2)
# --------------------------------------------------------------------------- #


def _chave_dedup(item_normalizado: dict[str, Any]) -> tuple[str, ...]:
    """Chave estavel de deduplicacao de um item ja normalizado.

    Preferencia: `ref_registro.id` (o identificador real do registro no
    portal). Sem id (ex.: despesas do Centi sem `Id` no payload), cai para
    (numero, data, valor) -- blueprint §3.2. `numero` vem de
    `ref_registro.numero` (nao de `titulo`, que tem fallback para
    `descricao` quando o portal nao traz numero -- ver `_normalizar_item`).
    """
    ref = item_normalizado.get("ref_registro") or {}
    rid = ref.get("id")
    if rid:
        return ("id", str(rid))
    return (
        "fallback",
        str(ref.get("numero", "")),
        str(item_normalizado.get("data", "")),
        str(item_normalizado.get("valor", "")),
    )


def _mesclar_normalizados(
    achados: dict[tuple[str, ...], dict[str, Any]],
    itens_normalizados: list[dict[str, Any]],
    origem: str,
) -> None:
    """Mescla itens JA normalizados em `achados`, unindo `origem` em duplicatas."""
    for norm in itens_normalizados:
        chave = _chave_dedup(norm)
        existente = achados.get(chave)
        if existente is None:
            novo = dict(norm)
            novo["origem"] = [origem]
            achados[chave] = novo
        elif origem not in existente["origem"]:
            existente["origem"].append(origem)


def _mesclar(
    achados: dict[tuple[str, ...], dict[str, Any]],
    itens_raw: list[dict[str, Any]],
    secao: str,
    origem: str,
) -> None:
    """Normaliza itens brutos do portal (`secao`) e mescla em `achados`."""
    _mesclar_normalizados(achados, [_normalizar_item(it, secao) for it in itens_raw], origem)


async def _coletar_despesas_combinado(
    cli: httpx.AsyncClient, mun: Municipio, nome: str, cnpj_digitos: str
) -> tuple[dict[tuple[str, ...], dict[str, Any]], bool, int | None, int | None]:
    """Despesas por nome/CNPJ: Centi (5 municipios) ou multi_request (Sen. Canedo).

    Returns:
        (achados, truncado, total_portal_nome, total_portal_cnpj). O caminho
        Centi devolve TODOS os registros do periodo numa chamada so (doc 02
        §1.2) -- nunca truncado. O caminho multi_request (Sen. Canedo) varre
        como as demais secoes e PODE truncar (`_MAX_PAGINAS`); a informacao e
        propagada para o chamador emitir aviso (F2 da revisao P1).
    """
    achados: dict[tuple[str, ...], dict[str, Any]] = {}
    if mun.slug in centi.MUNICIPIOS_CENTI:
        if cnpj_digitos:
            itens = await centi.buscar_despesas(cli, mun.url_base, cpf_cnpj=cnpj_digitos)
            _mesclar_normalizados(achados, itens, "cnpj")
        if nome:
            itens = await centi.buscar_despesas(cli, mun.url_base, credor=nome)
            _mesclar_normalizados(achados, itens, "nome")
        return achados, False, None, None
    # Senador Canedo: mesmo padrao multi_request das demais secoes (a rota
    # `despesas` existe em routes.py -> capacidades.resolver deriva o acao).
    try:
        cap = capacidades.resolver(mun.slug, "despesas")
    except SecaoIndisponivel:
        return achados, False, None, None
    truncado = False
    total_portal_nome: int | None = None
    total_portal_cnpj: int | None = None
    if nome:
        _, itens_nome, total_portal_nome, truncado_nome = await _coletar_termo(
            cli, mun.url_base, cap, nome
        )
        _mesclar(achados, itens_nome, "despesas", "nome")
        truncado = truncado or truncado_nome
    if cnpj_digitos:
        _, itens_cnpj, total_portal_cnpj, truncado_cnpj = await _coletar_documento(
            cli, mun.url_base, cap, cnpj_digitos
        )
        _mesclar(achados, itens_cnpj, "despesas", "cnpj")
        truncado = truncado or truncado_cnpj
    return achados, truncado, total_portal_nome, total_portal_cnpj


async def pesquisar_combinado(
    slug: str,
    nome: str | None = None,
    cnpj: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Busca pelo NOME e/ou CNPJ do mesmo fornecedor, sem duplicar registro.

    Historia 1 do blueprint (escritorio de advocacia): informa nome e/ou CNPJ
    e o sistema busca pelos dois, maximizando cobertura sem contar o mesmo
    contrato/dispensa/licitacao/despesa duas vezes (blueprint §3.2). Despesas
    vao via backend Centi (server-side, 1 chamada) nos 5 municipios cobertos;
    em Senador Canedo, via multi_request (mesmo padrao das demais secoes).
    Contratos/dispensas/licitacoes continuam no caminho existente
    (server-side-com-fallback para nome, varredura+filtro para CNPJ).

    Args:
        slug: municipio.
        nome: termo/nome do fornecedor (opcional).
        cnpj: CNPJ do fornecedor, com ou sem mascara (opcional).
        client: httpx.AsyncClient opcional (injetavel em teste).

    Returns:
        {
          "municipio": {"slug":..., "nome":...}, "nome":..., "cnpj":...,
          "grupos": [{"secao":..., "total":..., "truncado":...,
                      "modo_nome":..., "modo_cnpj":...,
                      "total_portal_nome":..., "total_portal_cnpj":...,
                      "itens":[{..., "origem":["nome","cnpj"]}]}],
          "avisos": [...]
        }
        `truncado=True` quando a varredura de nome e/ou de cnpj bateu o teto
        de paginas (`_MAX_PAGINAS`) e o resultado pode estar incompleto (F2
        da revisao P1) -- mesmo sinal que `pesquisar()` ja da por secao.

    Raises:
        KeyError: municipio nao cadastrado.
        ValueError: nem nome nem cnpj informados.
        PortalError: nenhuma secao respondeu.
    """
    mun = get_mun(slug)  # KeyError se nao cadastrado
    nome = (nome or "").strip()
    cnpj_digitos = _so_digitos(cnpj or "")
    if not nome and not cnpj_digitos:
        raise ValueError("Informe nome e/ou CNPJ para a busca combinada.")

    disponiveis = set(capacidades.routes.secoes_disponiveis(slug))
    avisos: list[str] = []
    grupos: list[dict[str, Any]] = []
    secoes_tentadas = 0
    secoes_falharam = 0

    fechar = client is None
    cli = client or _novo_client()
    try:
        for secao in capacidades.SECOES_ENTIDADE:
            if secao not in disponiveis:
                continue
            try:
                cap = capacidades.resolver(slug, secao)
            except SecaoIndisponivel:
                continue
            secoes_tentadas += 1
            achados: dict[tuple[str, ...], dict[str, Any]] = {}
            truncado_secao = False
            modo_nome: str | None = None
            modo_cnpj: str | None = None
            total_portal_nome: int | None = None
            total_portal_cnpj: int | None = None
            try:
                if nome:
                    modo_nome, itens_nome, total_portal_nome, truncado_nome = await _coletar_termo(
                        cli, mun.url_base, cap, nome
                    )
                    _mesclar(achados, itens_nome, secao, "nome")
                    truncado_secao = truncado_secao or truncado_nome
                if cnpj_digitos:
                    modo_cnpj, itens_cnpj, total_portal_cnpj, truncado_cnpj = await _coletar_documento(
                        cli, mun.url_base, cap, cnpj_digitos
                    )
                    _mesclar(achados, itens_cnpj, secao, "cnpj")
                    truncado_secao = truncado_secao or truncado_cnpj
            except PortalError as exc:
                secoes_falharam += 1
                avisos.append(
                    f"Nao foi possivel consultar a secao '{secao}' do portal "
                    f"({exc}); mostrando o restante."
                )
                continue
            if achados:
                grupos.append(
                    {
                        "secao": secao,
                        "total": len(achados),
                        "itens": list(achados.values()),
                        "truncado": truncado_secao,
                        "modo_nome": modo_nome,
                        "modo_cnpj": modo_cnpj,
                        "total_portal_nome": total_portal_nome,
                        "total_portal_cnpj": total_portal_cnpj,
                    }
                )
                if truncado_secao:
                    avisos.append(
                        f"Secao '{secao}' teve varredura truncada na busca combinada "
                        f"(mais de {_MAX_PAGINAS * _PAGE} registros no portal); pode "
                        "nao ter trazido todos os itens."
                    )

        if "despesas" in disponiveis:
            secoes_tentadas += 1
            try:
                achados_despesas, truncado_despesas, tp_nome, tp_cnpj = (
                    await _coletar_despesas_combinado(cli, mun, nome, cnpj_digitos)
                )
            except (PortalError, centi.PortalError) as exc:
                secoes_falharam += 1
                avisos.append(
                    f"Nao foi possivel consultar despesas do portal ({exc}); "
                    "mostrando o restante."
                )
            else:
                if achados_despesas:
                    grupos.append(
                        {
                            "secao": "despesas",
                            "total": len(achados_despesas),
                            "itens": list(achados_despesas.values()),
                            "truncado": truncado_despesas,
                            "total_portal_nome": tp_nome,
                            "total_portal_cnpj": tp_cnpj,
                        }
                    )
                    if truncado_despesas:
                        avisos.append(
                            "Secao 'despesas' teve varredura truncada na busca combinada "
                            f"(mais de {_MAX_PAGINAS * _PAGE} registros no portal); pode "
                            "nao ter trazido todos os itens."
                        )

        if secoes_tentadas and secoes_falharam == secoes_tentadas:
            raise PortalError(
                "Nao foi possivel consultar nenhuma secao do portal apos "
                "as tentativas de retry (portal parece fora do ar)."
            )
    finally:
        if fechar:
            await cli.aclose()

    return {
        "municipio": {"slug": mun.slug, "nome": mun.nome},
        "nome": nome,
        "cnpj": cnpj_digitos,
        "grupos": grupos,
        "avisos": avisos,
    }


__all__ = ["detectar_tipo", "pesquisar", "pesquisar_folha", "pesquisar_combinado", "PortalError"]
