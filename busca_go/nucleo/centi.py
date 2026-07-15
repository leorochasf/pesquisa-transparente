"""Cliente do backend Centi (`POST /api/centi`) para despesas/empenhos.

5 dos 6 municipios (todos menos Senador Canedo) expoem despesas/receitas por
um backend .NET WCF de terceiro ("Centi"), endpoint proprio `POST <url_base>/
api/centi`, corpo form-urlencoded SEM o envelope `multi_request` (doc 02
§1.2). Devolve TODOS os registros do periodo filtrado numa unica chamada (sem
paginacao de 50) -- busca por fornecedor NAO precisa varrer.

Armadilha confirmada (doc 02 §5): o filtro `cpf_cnpj` so funciona SEM
pontuacao -- com mascara ("02.292.266/0001-80") falha SILENCIOSAMENTE (200 OK,
lista vazia). `normalizar_documento()` torna a normalizacao obrigatoria, nao
uma otimizacao.

Senador Canedo NAO usa este backend; despesas la seguem o padrao `/api
multi_request` ja existente (`despesas_frl/listar`), resolvido por
`capacidades.resolver`/`entidade._coletar_documento`/`_coletar_termo`.
"""

from __future__ import annotations

import asyncio
import os
import random
import re
from datetime import date
from typing import Any

import httpx

# UA de desktop obrigatorio: mesma exigencia do driver multi_request
# (`entidade._UA_CHROME`) -- o WAF do NucleoGov bloqueia UA HeadlessChrome.
_UA_CHROME = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

# Municipios cujo backend de despesas/receitas e o Centi (doc 02 §1.2).
# Senador Canedo fica de fora -- usa multi_request (`despesas_frl/listar`).
MUNICIPIOS_CENTI: frozenset[str] = frozenset(
    {"rioverde", "trindade", "cristalina", "itumbiara", "saomigueldoaraguaia"}
)

# Cobre o periodo em que o portal tem dado. Um range estreito trunca sem
# aviso: o mesmo CNPJ (TJ-GO em Trindade) devolveu 40 itens filtrando so o
# ano corrente e 428 com o historico completo (verificado ao vivo nesta
# missao, 2026-07-14).
_DATA_INICIO_PADRAO = "01/01/2000"

_TENTATIVAS_RETRY = 3
_BACKOFF_SEGUNDOS = 0.5

# Retry para HTTP 202 -- bloqueio SUAVE do WAF do NucleoGov (mesmo host de
# `entidade._post_com_retry`; ver F3 da aceitacao final). Mecanismo proprio,
# separado do de timeout/conexao acima: backoff educado e limitado, honra
# `Retry-After` quando o portal manda.
_TENTATIVAS_202 = int(os.getenv("BUSCA_GO_202_TENTATIVAS", "4"))
_BACKOFF_202_MIN_S = float(os.getenv("BUSCA_GO_202_BACKOFF_MIN_S", "2.0"))
_BACKOFF_202_MAX_S = float(os.getenv("BUSCA_GO_202_BACKOFF_MAX_S", "15.0"))


class PortalError(RuntimeError):
    """O backend Centi recusou/quebrou a requisicao (nao e vazio legitimo)."""


def normalizar_documento(doc: str) -> str:
    """So digitos -- o backend Centi filtra `cpf_cnpj` SEM pontuacao (doc 02 §5).

    Enviar com mascara faz o filtro falhar silenciosamente (200 OK, lista
    vazia); normalizar aqui e obrigatorio, nao opcional.
    """
    return re.sub(r"\D", "", doc or "")


_BASE_PARAMS: dict[str, str] = {
    "numero": "0",
    "processo": "0",
    "credor": "",
    "cpf_cnpj": "",
    "ano": "0",
    "valor_inicial": "0",
    "valor_final": "0",
    "id_orgao": "0",
    "id_funcao": "0",
    "licitacao": "0",
    "elemento": "",
    "sub_funcao": "",
    "dp_acao": "",
    "covid": "",
}


def _retry_after_segundos(resp: httpx.Response) -> float | None:
    valor = resp.headers.get("Retry-After")
    if not valor:
        return None
    try:
        return float(valor)
    except ValueError:
        return None


def _espera_202(tentativa: int, retry_after: float | None) -> float:
    if retry_after is not None:
        return max(_BACKOFF_202_MIN_S, min(retry_after, _BACKOFF_202_MAX_S))
    base = _BACKOFF_202_MIN_S * (tentativa + 1)
    jitter = random.uniform(0, _BACKOFF_202_MIN_S)
    return min(base + jitter, _BACKOFF_202_MAX_S)


async def _post_com_retry(
    client: httpx.AsyncClient, url: str, corpo: dict[str, Any]
) -> httpx.Response:
    """POST com retry para erros transitorios e para HTTP 202 (mesmo padrao de
    `entidade._post_com_retry` -- ver F3 da aceitacao final)."""
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
    raise PortalError(
        f"Falha de rede ao consultar o backend Centi: {ultimo_exc}"
    ) from ultimo_exc


def _normalizar_empenho(item: dict[str, Any]) -> dict[str, Any]:
    """EmpenhoItem do Centi -> mesmo formato de saida de `entidade._normalizar_item`.

    Nao ha PDF/anexo de despesa em nenhum municipio (doc 02 §3) -- `tem_anexos`
    e sempre False, nunca None (None em outras secoes significa "sob demanda").
    """
    return {
        "titulo": str(item.get("Numero") or ""),
        "descricao": str(item.get("Historico") or "").strip(),
        "fornecedor": str(item.get("Fornecedor") or ""),
        "documento": str(item.get("CpfCnpjCredor") or ""),
        "valor": str(item.get("ValorEmpenhado") or ""),
        "data": str(item.get("Data") or ""),
        "tem_aditivo": False,
        "ref_registro": {
            "id": str(item.get("Id") or ""),
            "numero": str(item.get("Numero") or ""),
            "ano": "",
        },
        "tem_anexos": False,
        "raw": item,
    }


async def buscar_despesas(
    client: httpx.AsyncClient,
    url_base: str,
    *,
    cpf_cnpj: str | None = None,
    credor: str | None = None,
    data_inicio: str | None = None,
    data_fim: str | None = None,
) -> list[dict[str, Any]]:
    """Busca despesas/empenhos no backend Centi -- 1 chamada, sem paginar.

    `cpf_cnpj` e normalizado aqui (so digitos) -- quem chama pode passar com
    ou sem mascara. Sem nenhum filtro o backend devolve o volume TOTAL do
    periodo (pode passar de 10k linhas nos municipios maiores); informe ao
    menos `cpf_cnpj` ou `credor`.

    Returns:
        Lista de itens normalizados (ver `_normalizar_empenho`).

    Raises:
        PortalError: status HTTP != 200, corpo nao-JSON, corpo JSON que nao e
            uma lista (resposta inesperada -- nunca vira `[]` fingindo
            sucesso), ou falha de rede persistente apos as tentativas de
            retry.
    """
    corpo = dict(_BASE_PARAMS)
    corpo["acao"] = "empenhos"
    corpo["data_inicio"] = data_inicio or _DATA_INICIO_PADRAO
    corpo["data_fim"] = data_fim or date.today().strftime("%d/%m/%Y")
    if cpf_cnpj:
        corpo["cpf_cnpj"] = normalizar_documento(cpf_cnpj)
    if credor:
        corpo["credor"] = credor

    try:
        resp = await _post_com_retry(client, f"{url_base}/api/centi", corpo)
    except httpx.HTTPError as exc:
        raise PortalError(f"Falha de rede ao consultar o backend Centi: {exc}") from exc
    if resp.status_code != 200:
        raise PortalError(f"O backend Centi recusou o acesso (HTTP {resp.status_code}).")
    try:
        dados = resp.json()
    except ValueError as exc:
        raise PortalError(f"Resposta invalida do backend Centi: {exc}") from exc
    if not isinstance(dados, list):
        # 200 com corpo que nao e lista (ex.: dict de erro do WCF, ou o
        # formato {"dados":[...]} que o proprio Centi usa em acao=receitas)
        # e anomalia, nao "vazio legitimo" -- nunca fingir sucesso com [].
        raise PortalError(
            "Resposta inesperada do backend Centi: esperava uma lista JSON, "
            f"veio {type(dados).__name__}."
        )
    return [_normalizar_empenho(it) for it in dados]


__all__ = ["MUNICIPIOS_CENTI", "PortalError", "normalizar_documento", "buscar_despesas"]
