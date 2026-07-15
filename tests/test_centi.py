"""Testes do cliente Centi (`POST /api/centi`): normalizacao de cpf_cnpj e parsing.

Sem rede: o POST /api/centi e stubado com httpx.MockTransport, reproduzindo o
formato real observado ao vivo (lista JSON direta de EmpenhoItem, doc 02 §1.2).
"""

from __future__ import annotations

from urllib.parse import parse_qs

import httpx
import pytest

from busca_go.nucleo import centi


def _client(transport):
    return httpx.AsyncClient(transport=transport, base_url="https://x")


# --------------------------------------------------------------------------- #
# Normalizacao de cpf_cnpj (doc 02 §5 -- a armadilha)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "bruto, digitos",
    [
        ("02.292.266/0001-80", "02292266000180"),
        ("02292266000180", "02292266000180"),
        ("054.xxx.xxx-96", "05496"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalizar_documento_so_digitos(bruto, digitos):
    assert centi.normalizar_documento(bruto) == digitos


async def test_buscar_despesas_envia_cpf_cnpj_ja_sem_pontuacao():
    """O corpo enviado ao portal SEMPRE tem cpf_cnpj so digitos, mesmo se quem
    chamou passou com mascara -- e exatamente a armadilha do doc 02 §5."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/centi"
        captured["form"] = parse_qs(request.content.decode())
        return httpx.Response(200, json=[])

    async with _client(httpx.MockTransport(handler)) as cli:
        await centi.buscar_despesas(cli, "https://x", cpf_cnpj="02.292.266/0001-80")

    assert captured["form"]["cpf_cnpj"][0] == "02292266000180"
    assert captured["form"]["acao"][0] == "empenhos"


async def test_buscar_despesas_normaliza_lista_para_formato_padrao():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "$type": "ServerAppWCF.Service.Portal.Controllers.EmpenhoItem, Wcf",
                    "Id": 203152,
                    "Numero": "203152",
                    "Data": "14/07/2026",
                    "Fornecedor": "TRIBUNAL DE JUSTICA DO ESTADO DE GOIAS",
                    "ValorEmpenhado": "2.124,890",
                    "CpfCnpjCredor": "02.292.266/0001-80",
                    "Historico": "EMISSAO DE EMPENHO...",
                }
            ],
        )

    async with _client(httpx.MockTransport(handler)) as cli:
        itens = await centi.buscar_despesas(cli, "https://x", cpf_cnpj="02292266000180")

    assert len(itens) == 1
    item = itens[0]
    assert item["titulo"] == "203152"
    assert item["fornecedor"] == "TRIBUNAL DE JUSTICA DO ESTADO DE GOIAS"
    assert item["valor"] == "2.124,890"
    assert item["data"] == "14/07/2026"
    assert item["documento"] == "02.292.266/0001-80"
    assert item["tem_anexos"] is False  # nenhum municipio expoe PDF de despesa (doc 02 §3)
    assert item["ref_registro"]["id"] == "203152"
    assert item["raw"]["Id"] == 203152


async def test_buscar_despesas_resposta_nao_lista_vira_portalerror():
    """200 com corpo que nao e lista (ex.: dict de erro do WCF, ou o formato
    {"dados":[...]} que o proprio Centi usa em acao=receitas) e anomalia --
    nunca vira [] fingindo sucesso, vira PortalError (mesmo padrao 502 honesto
    de HTTP != 200 e corpo nao-JSON)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"erro": "acao invalida"})

    async with _client(httpx.MockTransport(handler)) as cli:
        with pytest.raises(centi.PortalError):
            await centi.buscar_despesas(cli, "https://x", cpf_cnpj="123")


async def test_buscar_despesas_http_erro_vira_portalerror():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="down")

    async with _client(httpx.MockTransport(handler)) as cli:
        with pytest.raises(centi.PortalError):
            await centi.buscar_despesas(cli, "https://x", cpf_cnpj="123")


def test_municipios_centi_exclui_senador_canedo():
    assert "senadorcanedo" not in centi.MUNICIPIOS_CENTI
    assert "trindade" in centi.MUNICIPIOS_CENTI


# --------------------------------------------------------------------------- #
# Retry para HTTP 202 (bloqueio suave do WAF, mesmo host de entidade.py) --
# F3 da aceitacao final.
# --------------------------------------------------------------------------- #


async def test_buscar_despesas_202_depois_200_recupera_com_retry(monkeypatch):
    monkeypatch.setattr(centi, "_BACKOFF_202_MIN_S", 0.01)
    monkeypatch.setattr(centi, "_BACKOFF_202_MAX_S", 0.02)
    chamadas = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        chamadas["n"] += 1
        if chamadas["n"] < 3:
            return httpx.Response(202, json={})
        return httpx.Response(200, json=[])

    async with _client(httpx.MockTransport(handler)) as cli:
        itens = await centi.buscar_despesas(cli, "https://x", cpf_cnpj="123")

    assert itens == []
    assert chamadas["n"] == 3


async def test_buscar_despesas_202_persistente_levanta_portalerror_especifico(monkeypatch):
    monkeypatch.setattr(centi, "_BACKOFF_202_MIN_S", 0.01)
    monkeypatch.setattr(centi, "_BACKOFF_202_MAX_S", 0.02)
    monkeypatch.setattr(centi, "_TENTATIVAS_202", 2)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(202, json={})

    async with _client(httpx.MockTransport(handler)) as cli:
        with pytest.raises(centi.PortalError) as excinfo:
            await centi.buscar_despesas(cli, "https://x", cpf_cnpj="123")

    assert "recusou temporariamente" in str(excinfo.value)
