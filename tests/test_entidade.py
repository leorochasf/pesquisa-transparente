"""Testes da busca por entidade (deteccao, driver, server-side-vs-fallback, agregacao).

Sem rede: o POST /api multi_request e stubado com httpx.MockTransport, que
reproduz o formato real observado ao vivo ({"k1":{"total":N,"dados":[...]}}),
incluindo paginacao por `limit` e filtragem (ou nao) pelo campo de busca.
"""

from __future__ import annotations

import json
from urllib.parse import parse_qs

import httpx
import pytest

from busca_go.nucleo import capacidades, entidade


# --------------------------------------------------------------------------- #
# Deteccao de entidade
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "entrada, tipo, needle",
    [
        ("45.160.810/0001-43", "cnpj", "45160810000143"),
        ("45160810000143", "cnpj", "45160810000143"),
        ("123.456.789-09", "cpf", "12345678909"),
        ("12345678909", "cpf", "12345678909"),
        ("FL CONSTRUTORA LTDA", "termo", "FL CONSTRUTORA LTDA"),
        ("PREGAO 2024", "termo", "PREGAO 2024"),  # tem digitos, mas tambem letras
        ("12345", "termo", "12345"),  # 5 digitos != 11/14
        ("  espaço  ", "termo", "espaço"),
    ],
)
def test_detectar_tipo(entrada, tipo, needle):
    assert entidade.detectar_tipo(entrada) == (tipo, needle)


# --------------------------------------------------------------------------- #
# Portal falso (MockTransport)
# --------------------------------------------------------------------------- #

# Datasets por acao. Cada linha e um dict como o portal devolve.
_CONTRATOS = [
    {"numero": "0324/26", "contratado_nome": "FL CONSTRUTORA LTDA",
     "contratado_documento": "45.160.810/0001-43", "objeto": "PAVIMENTACAO DE VIAS",
     "valor": "100,00", "aditivos": [{"n": 1}]},
    {"numero": "0100/26", "contratado_nome": "OUTRA EMPRESA SA",
     "contratado_documento": "11.111.111/0001-11", "objeto": "MERENDA ESCOLAR",
     "valor": "50,00", "aditivos": []},
    {"numero": "0200/26", "contratado_nome": "FL CONSTRUTORA LTDA",
     "contratado_documento": "45.160.810/0001-43", "objeto": "REFORMA DE PRACA",
     "valor": "80,00", "aditivos": []},
]
_LICITACOES = [
    {"numero_processo": "023508/26", "modalidade": "PREGAO ELETRONICO",
     "descricao": "PAVIMENTACAO DE VIAS URBANAS", "valor_estimado": "300,00"},
    {"numero_processo": "099999/26", "modalidade": "CONCORRENCIA",
     "descricao": "AQUISICAO DE VEICULOS", "valor_estimado": "500,00"},
]
_DISPENSAS = [
    {"numero_processo": "059134/26", "modalidade": "INEXIGIBILIDADE",
     "descricao": "LOCACAO DE IMOVEL PARA PAVIMENTACAO", "valor_estimado": "92,00"},
]
_FOLHA = [
    # dois MARIA DA SILVA homonimos (matriculas distintas) -> devem ser 2 servidores
    {"matricula": 111, "nome": "MARIA DA SILVA", "cargo": "PROFESSORA",
     "lotacao": "SEMED", "orgao": "PREFEITURA", "referencia": "A1", "tipo_folha": "Folha Mensal",
     "cpf": "xxx.xxx.xxx-xx", "mes": "06", "ano": "2026", "total_liquido": "3.000,00"},
    {"matricula": 222, "nome": "MARIA DA SILVA", "cargo": "ENFERMEIRA",
     "lotacao": "SAUDE", "orgao": "FMS", "referencia": "B2", "tipo_folha": "Folha Mensal",
     "cpf": "xxx.xxx.xxx-xx", "mes": "06", "ano": "2026", "total_liquido": "4.500,00"},
    {"nome": "JOAO SOUZA", "cargo": "MOTORISTA", "matricula": 333,
     "cpf": "xxx.xxx.xxx-xx", "mes": "06", "ano": "2026", "total_liquido": "2.000,00"},
]


def _folter(rows, field, term):
    """Simula o filtro server-side do portal por substring no `field`."""
    t = term.lower()
    out = []
    for r in rows:
        hay = " ".join(str(v) for v in r.values()).lower()
        if t in hay:
            out.append(r)
    return out


def make_portal(*, contratos_busca_ok=True, licitacoes_busca_ok=True):
    """Cria um MockTransport que responde ao POST /api como o portal real.

    contratos_busca_ok=False simula o campo de busca QUEBRADO (ignora txtbusca,
    devolve o dataset inteiro) — dispara o fallback de varredura no app.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api"
        form = parse_qs(request.content.decode())
        params = json.loads(form["params"][0])
        blk = params["k1"]
        acao = blk["acao"]
        off_s, cnt_s = blk["limit"].split(",")
        offset, count = int(off_s), int(cnt_s)
        termo = blk.get("txtbusca") or blk.get("busca")

        if acao == "contratos_frl/listar":
            rows = _CONTRATOS
            if termo and contratos_busca_ok:
                rows = _folter(rows, None, termo)
        elif acao == "licitacoes_frl/listar":
            base = _DISPENSAS if blk.get("dispensas") == "1" else _LICITACOES
            rows = base
            if termo and licitacoes_busca_ok:
                rows = _folter(rows, None, termo)
        elif acao == "servidores_frl/listar":
            rows = _FOLHA
            if termo:
                rows = _folter(rows, None, termo)
        else:
            # acao desconhecida: portal devolve lista vazia no k1 (nao dict)
            return httpx.Response(200, json=[])

        total = len(rows)
        page = rows[offset:offset + count]
        return httpx.Response(200, json={"k1": {"total": total, "dados": page}})

    return httpx.MockTransport(handler)


def _client(transport):
    return httpx.AsyncClient(transport=transport, base_url="https://x")


# --------------------------------------------------------------------------- #
# Driver: monta o payload certo
# --------------------------------------------------------------------------- #


async def test_driver_monta_payload():
    """_multi envia acao, limit e campo de busca no formato multi_request."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        form = parse_qs(request.content.decode())
        captured["multi_request"] = form["multi_request"][0]
        captured["params"] = json.loads(form["params"][0])
        return httpx.Response(200, json={"k1": {"total": 0, "dados": []}})

    async with _client(httpx.MockTransport(handler)) as cli:
        await entidade._multi(cli, "https://x", "contratos_frl/listar", {"txtbusca": "ACME"}, 50, 50)

    assert captured["multi_request"] == "true"
    k1 = captured["params"]["k1"]
    assert k1["acao"] == "contratos_frl/listar"
    assert k1["limit"] == "50, 50"
    assert k1["txtbusca"] == "ACME"


async def test_multi_k1_lista_vira_vazio():
    """k1 vindo como lista (acao invalida) nao levanta — vira total 0."""
    async with _client(make_portal()) as cli:
        out = await entidade._multi(cli, "https://x", "acao_inexistente/listar", {}, 0, 50)
    assert out == {"total": 0, "dados": []}


async def test_multi_http_erro_vira_portalerror():
    def handler(request):
        return httpx.Response(503, text="down")

    async with _client(httpx.MockTransport(handler)) as cli:
        with pytest.raises(entidade.PortalError):
            await entidade._multi(cli, "https://x", "contratos_frl/listar", {}, 0, 50)


# --------------------------------------------------------------------------- #
# Retry + mensagem de erro nao-truncada (bugfix Ui90cB65-35)
# --------------------------------------------------------------------------- #


async def test_multi_retry_recupera_de_timeout_transitorio():
    """Timeout nas 2 primeiras tentativas, sucesso na 3a -> nao levanta."""
    chamadas = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        chamadas["n"] += 1
        if chamadas["n"] < 3:
            raise httpx.ReadTimeout("boom", request=request)
        return httpx.Response(200, json={"k1": {"total": 0, "dados": []}})

    async with _client(httpx.MockTransport(handler)) as cli:
        out = await entidade._multi(cli, "https://x", "contratos_frl/listar", {}, 0, 50)

    assert out == {"total": 0, "dados": []}
    assert chamadas["n"] == 3


async def test_multi_timeout_persistente_leva_portalerror_com_mensagem_completa():
    """Timeout em TODAS as tentativas -> PortalError com mensagem sem truncar."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("", request=request)  # str(exc) vazio (caso real)

    async with _client(httpx.MockTransport(handler)) as cli:
        with pytest.raises(entidade.PortalError) as excinfo:
            await entidade._multi(cli, "https://x", "contratos_frl/listar", {}, 0, 50)

    msg = str(excinfo.value)
    assert not msg.rstrip().endswith(":")
    assert "ReadTimeout" in msg


async def test_multi_202_depois_200_recupera_com_retry(monkeypatch):
    """202 (bloqueio suave do WAF) nas 2 primeiras tentativas, 200 na 3a -> sucesso."""
    monkeypatch.setattr(entidade, "_BACKOFF_202_MIN_S", 0.01)
    monkeypatch.setattr(entidade, "_BACKOFF_202_MAX_S", 0.02)
    chamadas = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        chamadas["n"] += 1
        if chamadas["n"] < 3:
            return httpx.Response(202, json={})
        return httpx.Response(200, json={"k1": {"total": 0, "dados": []}})

    async with _client(httpx.MockTransport(handler)) as cli:
        out = await entidade._multi(cli, "https://x", "contratos_frl/listar", {}, 0, 50)

    assert out == {"total": 0, "dados": []}
    assert chamadas["n"] == 3


async def test_multi_202_persistente_levanta_portalerror_especifico(monkeypatch):
    """202 em todas as tentativas -> PortalError com mensagem especifica (nao a generica de rede)."""
    monkeypatch.setattr(entidade, "_BACKOFF_202_MIN_S", 0.01)
    monkeypatch.setattr(entidade, "_BACKOFF_202_MAX_S", 0.02)
    monkeypatch.setattr(entidade, "_TENTATIVAS_202", 2)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(202, json={})

    async with _client(httpx.MockTransport(handler)) as cli:
        with pytest.raises(entidade.PortalError) as excinfo:
            await entidade._multi(cli, "https://x", "contratos_frl/listar", {}, 0, 50)

    assert "recusou temporariamente" in str(excinfo.value)


def test_espera_202_honra_retry_after_dentro_do_teto():
    """Com Retry-After, a espera usa o valor do portal (limitado por MIN/MAX)."""
    assert entidade._espera_202(0, 5.0) == 5.0
    # Retry-After acima do teto maximo -> limitado (nao espera tempo desproporcional).
    assert entidade._espera_202(0, 999.0) == entidade._BACKOFF_202_MAX_S
    # Retry-After abaixo do minimo -> respeita o piso educado.
    assert entidade._espera_202(0, 0.0) == entidade._BACKOFF_202_MIN_S


def test_espera_202_sem_retry_after_cresce_e_respeita_teto():
    """Sem Retry-After, backoff cresce por tentativa mas nunca passa do teto maximo."""
    espera_0 = entidade._espera_202(0, None)
    espera_1 = entidade._espera_202(1, None)
    assert entidade._BACKOFF_202_MIN_S <= espera_0 <= entidade._BACKOFF_202_MAX_S
    assert entidade._BACKOFF_202_MIN_S <= espera_1 <= entidade._BACKOFF_202_MAX_S


def test_retry_after_segundos_parseia_cabecalho():
    resp_com = httpx.Response(202, headers={"Retry-After": "7"})
    resp_sem = httpx.Response(202)
    resp_invalido = httpx.Response(202, headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"})
    assert entidade._retry_after_segundos(resp_com) == 7.0
    assert entidade._retry_after_segundos(resp_sem) is None
    assert entidade._retry_after_segundos(resp_invalido) is None  # formato data: cai no backoff padrao


# --------------------------------------------------------------------------- #
# Caminho folha-only: sem varrer secoes documentais (F4 da aceitacao final)
# --------------------------------------------------------------------------- #


def _handler_folha_only(request: httpx.Request) -> httpx.Response:
    """Falha (500) se alguma secao documental for tocada; so responde folha."""
    form = parse_qs(request.content.decode())
    params = json.loads(form["params"][0])
    acao = params["k1"]["acao"]
    if acao in ("contratos_frl/listar", "licitacoes_frl/listar"):
        return httpx.Response(500, text="nao deveria varrer secao documental para folha-only")
    if acao == "servidores_frl/listar":
        blk = params["k1"]
        off_s, cnt_s = blk["limit"].split(",")
        offset, count = int(off_s), int(cnt_s)
        termo = blk.get("txtbusca") or blk.get("busca")
        rows = _folter(_FOLHA, None, termo) if termo else _FOLHA
        return httpx.Response(200, json={"k1": {"total": len(rows), "dados": rows[offset:offset + count]}})
    return httpx.Response(200, json={"k1": {"total": 0, "dados": []}})


async def test_pesquisar_secoes_folha_only_nao_toca_documentais():
    """secoes=['folha'] vai direto a folha; um erro nas secoes documentais nao aparece."""
    async with _client(httpx.MockTransport(_handler_folha_only)) as cli:
        res = await entidade.pesquisar(
            "senadorcanedo", "MARIA DA SILVA", ano=2026, mes=6, client=cli, secoes=["folha"]
        )

    secoes = {g["secao"] for g in res["grupos"]}
    assert secoes == {"folha"}
    assert not any("contratos" in a or "licitacoes" in a for a in res["avisos"])
    folha = next(g for g in res["grupos"] if g["secao"] == "folha")
    assert folha["total"] == 2


async def test_pesquisar_folha_atalho_e_folha_only():
    """`pesquisar_folha` e o atalho de `pesquisar(..., secoes=['folha'])`."""
    async with _client(httpx.MockTransport(_handler_folha_only)) as cli:
        res = await entidade.pesquisar_folha("senadorcanedo", "MARIA DA SILVA", ano=2026, mes=6, client=cli)

    secoes = {g["secao"] for g in res["grupos"]}
    assert secoes == {"folha"}
    folha = next(g for g in res["grupos"] if g["secao"] == "folha")
    assert folha["total"] == 2


async def test_pesquisar_uma_secao_falha_nao_derruba_a_busca():
    """Uma secao com timeout persistente: resultado vem com as demais + aviso."""

    def handler(request: httpx.Request) -> httpx.Response:
        form = parse_qs(request.content.decode())
        params = json.loads(form["params"][0])
        acao = params["k1"]["acao"]
        if acao == "contratos_frl/listar":
            raise httpx.ReadTimeout("", request=request)
        if acao == "licitacoes_frl/listar":
            blk = params["k1"]
            base = _DISPENSAS if blk.get("dispensas") == "1" else _LICITACOES
            off_s, cnt_s = blk["limit"].split(",")
            offset, count = int(off_s), int(cnt_s)
            page = base[offset:offset + count]
            return httpx.Response(200, json={"k1": {"total": len(base), "dados": page}})
        return httpx.Response(200, json={"k1": {"total": 0, "dados": []}})

    async with _client(httpx.MockTransport(handler)) as cli:
        res = await entidade.pesquisar("senadorcanedo", "PAVIMENTACAO", client=cli)

    grupos = {g["secao"]: g for g in res["grupos"]}
    assert "contratos" not in grupos  # a secao que falhou nao aparece
    assert grupos["licitacoes"]["total"] >= 1  # as demais seguiram normalmente
    assert any(
        "contratos" in a and "restante" in a for a in res["avisos"]
    )  # aviso claro da secao que falhou


async def test_pesquisar_todas_as_secoes_falham_levanta_portalerror():
    """Portal totalmente fora do ar (todas as secoes falham) -> PortalError (502)."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("", request=request)

    async with _client(httpx.MockTransport(handler)) as cli:
        with pytest.raises(entidade.PortalError):
            await entidade.pesquisar("senadorcanedo", "PAVIMENTACAO", client=cli)


# --------------------------------------------------------------------------- #
# Server-side-primeiro-com-fallback
# --------------------------------------------------------------------------- #


async def test_termo_server_side_quando_filtra():
    """Busca por termo usa server-side quando o portal filtra de verdade."""
    cap = capacidades.resolver("senadorcanedo", "contratos")
    async with _client(make_portal(contratos_busca_ok=True)) as cli:
        modo, itens, total, trunc = await entidade._coletar_termo(
            cli, "https://x", cap, "FL CONSTRUTORA"
        )
    assert modo == "server"
    assert len(itens) == 2  # os dois contratos da FL CONSTRUTORA
    assert all("FL CONSTRUTORA" in i["contratado_nome"] for i in itens)


async def test_termo_fallback_quando_busca_quebrada():
    """Campo de busca quebrado (ignora o termo) -> fallback de varredura+filtro."""
    cap = capacidades.resolver("senadorcanedo", "contratos")
    async with _client(make_portal(contratos_busca_ok=False)) as cli:
        modo, itens, total, trunc = await entidade._coletar_termo(
            cli, "https://x", cap, "FL CONSTRUTORA"
        )
    assert modo == "varredura"
    # o portal devolveu TODOS (busca quebrada); o filtro local isolou os 2 certos
    assert len(itens) == 2
    assert all("FL CONSTRUTORA" in i["contratado_nome"] for i in itens)


async def test_documento_sempre_varre_e_filtra_local():
    """CNPJ nao e indexado -> sempre varredura + filtro local pelo documento."""
    cap = capacidades.resolver("senadorcanedo", "contratos")
    async with _client(make_portal()) as cli:
        modo, itens, total, trunc = await entidade._coletar_documento(
            cli, "https://x", cap, "45160810000143"
        )
    assert modo == "varredura"
    assert len(itens) == 2
    assert all(entidade._so_digitos(i["contratado_documento"]) == "45160810000143" for i in itens)


# --------------------------------------------------------------------------- #
# Caldazinha: sabor "megasoft" da folha (item 3L54H3Sr-29)
# --------------------------------------------------------------------------- #

# 3 servidores; PEDRO aparece na pagina 2 quando tamanhoDaPagina=50 e ha >50
# registros -- usado para validar a conversao offset -> numero de pagina.
_FOLHA_MEGASOFT = [
    {"matricula": 901, "nome": "ADAO TESTE DE EXEMPLO", "cargo": "AGENTE COMUNITARIO",
     "departamento": "FMS - AGENTE SAUDE", "tipoDeVinculo": "Concursado",
     "proventos": 4214.6, "descontos": 1658.67, "totalLiquido": 2555.93,
     "cpf": "xxx.795.191-xx", "mes": "06", "ano": 2026},
    {"matricula": 902, "nome": "ADRIANA TESTE DE EXEMPLO", "cargo": "PENSIONISTA",
     "departamento": "PENSIONISTAS", "tipoDeVinculo": "Pensionista (Vitalicio)",
     "proventos": 2658.67, "descontos": 0, "totalLiquido": 2658.67,
     "cpf": "xxx.467.741-xx", "mes": "06", "ano": 2026},
]


def _handler_megasoft(request: httpx.Request) -> httpx.Response:
    """Simula o portal `_mg` real: pagina/tamanhoDaPagina (nao limit), le
    k1.registros (nao k1.dados), exige codigosDoOrgao, busca por
    nomeDoFuncionario (nao txtbusca)."""
    form = parse_qs(request.content.decode())
    params = json.loads(form["params"][0])
    blk = params["k1"]
    assert blk["acao"] == "megasoft/servidores"
    assert "limit" not in blk
    assert blk["codigosDoOrgao"] == "22,23,24,25,26"
    pagina, tamanho = blk["pagina"], blk["tamanhoDaPagina"]
    assert pagina == 1  # unico dataset de teste cabe numa pagina
    termo = blk.get("nomeDoFuncionario")
    rows = _FOLHA_MEGASOFT
    if termo:
        rows = [r for r in rows if termo.lower() in r["nome"].lower()]
    return httpx.Response(200, json={"k1": {"total": len(rows), "registros": rows[:tamanho]}})


async def test_multi_megasoft_monta_payload_pagina_e_le_registros():
    """modo_api='megasoft': paginacao por pagina/tamanhoDaPagina, le k1.registros."""
    async with _client(httpx.MockTransport(_handler_megasoft)) as cli:
        out = await entidade._multi(
            cli, "https://x", "megasoft/servidores",
            {"nomeDoFuncionario": "ADAO", "codigosDoOrgao": "22,23,24,25,26"},
            0, 50, "megasoft",
        )
    assert out == {"total": 1, "dados": _FOLHA_MEGASOFT[:1]}


async def test_multi_megasoft_converte_offset_em_numero_de_pagina():
    """offset=50 com count=50 -> pagina=2 (nao offset bruto no payload)."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        params = json.loads(parse_qs(request.content.decode())["params"][0])
        captured["pagina"] = params["k1"]["pagina"]
        return httpx.Response(200, json={"k1": {"total": 0, "registros": []}})

    async with _client(httpx.MockTransport(handler)) as cli:
        await entidade._multi(cli, "https://x", "megasoft/servidores", {}, 50, 50, "megasoft")

    assert captured["pagina"] == 2


async def test_grupo_folha_caldazinha_usa_capacidade_megasoft():
    """`pesquisar_folha` em caldazinha usa o sabor megasoft de ponta a ponta,
    incluindo o extra fixo `codigosDoOrgao` (sem ele o portal real zera)."""
    async with _client(httpx.MockTransport(_handler_megasoft)) as cli:
        res = await entidade.pesquisar_folha("caldazinha", "ADAO", ano=2026, mes=6, client=cli)

    folha = next(g for g in res["grupos"] if g["secao"] == "folha")
    assert folha["total"] == 1
    assert folha["itens"][0]["nome"] == "ADAO TESTE DE EXEMPLO"
    assert folha["itens"][0]["cpf_mascarado"] == "xxx.795.191-xx"


# --------------------------------------------------------------------------- #
# Agregacao / agrupamento
# --------------------------------------------------------------------------- #


async def test_pesquisar_termo_agrega_por_secao_e_marca_aditivo():
    """Termo 'PAVIMENTACAO' cruza >=2 secoes; aditivo marcado dentro de contratos."""
    async with _client(make_portal()) as cli:
        res = await entidade.pesquisar("senadorcanedo", "PAVIMENTACAO", client=cli)

    assert res["tipo"] == "termo"
    grupos = {g["secao"]: g for g in res["grupos"]}
    # PAVIMENTACAO aparece em contratos, licitacoes e dispensas
    assert grupos["contratos"]["total"] >= 1
    assert grupos["licitacoes"]["total"] >= 1
    assert grupos["dispensas"]["total"] >= 1
    # >= 2 secoes com resultado (requisito do agregador)
    com_itens = [s for s, g in grupos.items() if g["total"] > 0 and s != "folha"]
    assert len(com_itens) >= 2
    # o contrato PAVIMENTACAO da FL CONSTRUTORA tem aditivo
    contr = grupos["contratos"]["itens"]
    assert any(i["tem_aditivo"] for i in contr)
    assert any("aditivo" in a.lower() for a in res["avisos"])


async def test_pesquisar_cnpj_agrega_e_avisa():
    """CNPJ: agrega por documento e emite aviso de que CNPJ nao e indexado."""
    async with _client(make_portal()) as cli:
        res = await entidade.pesquisar("senadorcanedo", "45.160.810/0001-43", client=cli)

    assert res["tipo"] == "cnpj"
    grupos = {g["secao"]: g for g in res["grupos"]}
    assert grupos["contratos"]["total"] == 2
    assert all(g["modo"] == "varredura" for s, g in grupos.items() if s != "folha")
    assert any("CNPJ nao e indexado" in a for a in res["avisos"])


async def test_pesquisar_folha_por_nome_diferencia_homonimos():
    """Folha por nome: linhas carregam matricula/cargo/lotacao e agrupam por servidor."""
    async with _client(make_portal()) as cli:
        res = await entidade.pesquisar("senadorcanedo", "MARIA DA SILVA", ano=2026, mes=6, client=cli)

    folha = next(g for g in res["grupos"] if g["secao"] == "folha")
    assert folha["total"] == 2  # duas linhas MARIA DA SILVA
    # cada item plano carrega os campos de diferenciacao (nao so em raw)
    it0 = folha["itens"][0]
    assert it0["matricula"] and it0["cargo"] and it0["lotacao"] and it0["tipo_folha"]
    # agrupadas por matricula -> 2 servidores homonimos distintos
    servidores = folha["servidores"]
    assert len(servidores) == 2
    assert {s["matricula"] for s in servidores} == {"111", "222"}
    assert all(len(s["folhas"]) == 1 for s in servidores)
    # aviso de homonimo emitido
    assert any("homonimo" in a.lower() for a in res["avisos"])


async def test_pesquisar_folha_cpf_suspenso():
    """CPF na folha esta suspenso: sem grupo de folha + aviso explicativo."""
    async with _client(make_portal()) as cli:
        res = await entidade.pesquisar("senadorcanedo", "123.456.789-09", ano=2026, mes=6, client=cli)

    assert res["tipo"] == "cpf"
    assert not any(g["secao"] == "folha" for g in res["grupos"])
    assert any("folha por CPF" in a or "CPF/CNPJ esta suspensa" in a for a in res["avisos"])


async def test_pesquisar_vazio():
    """Entrada vazia: sem grupos, com aviso."""
    async with _client(make_portal()) as cli:
        res = await entidade.pesquisar("senadorcanedo", "   ", client=cli)
    assert res["grupos"] == []
    assert res["avisos"]


# --------------------------------------------------------------------------- #
# Busca combinada nome+CNPJ com deduplicacao (blueprint §3.2)
# --------------------------------------------------------------------------- #


async def test_pesquisar_combinado_nao_duplica_contrato_achado_pelos_dois():
    """FL CONSTRUTORA casa por nome E por CNPJ no mesmo contrato -> 1 item so,
    com origem=["nome","cnpj"]. A secao despesas E consultada (Senador Canedo
    tem rota `despesas` em routes.py), mas o `make_portal` de teste responde
    vazio para acao desconhecida (`despesas_frl/listar`) -- entao ela nao
    aparece em `res["grupos"]`, sem afetar o assert de contratos."""
    async with _client(make_portal()) as cli:
        res = await entidade.pesquisar_combinado(
            "senadorcanedo", nome="FL CONSTRUTORA", cnpj="45.160.810/0001-43", client=cli
        )

    grupos = {g["secao"]: g for g in res["grupos"]}
    contratos = grupos["contratos"]
    # FL CONSTRUTORA tem 2 contratos reais (0324/26 e 0200/26) -- nao 4 (2x2).
    assert contratos["total"] == 2
    numeros = {i["titulo"] for i in contratos["itens"]}
    assert numeros == {"0324/26", "0200/26"}
    # cada item achado pelos dois caminhos carrega as duas origens.
    assert all(set(i["origem"]) == {"nome", "cnpj"} for i in contratos["itens"])


async def test_pesquisar_combinado_so_nome_marca_origem_unica():
    async with _client(make_portal()) as cli:
        res = await entidade.pesquisar_combinado("senadorcanedo", nome="FL CONSTRUTORA", client=cli)

    grupos = {g["secao"]: g for g in res["grupos"]}
    assert all(i["origem"] == ["nome"] for i in grupos["contratos"]["itens"])


async def test_pesquisar_combinado_sem_nome_e_sem_cnpj_levanta_valueerror():
    async with _client(make_portal()) as cli:
        with pytest.raises(ValueError):
            await entidade.pesquisar_combinado("senadorcanedo", client=cli)


async def test_pesquisar_combinado_despesas_via_centi_dedup_entre_credor_e_cpf_cnpj():
    """Trindade (municipio Centi): mesmo empenho achado por `credor` e por
    `cpf_cnpj` -> 1 item so no grupo despesas, origem com os dois canais."""
    empenho = {
        "Id": 203152,
        "Numero": "203152",
        "Data": "14/07/2026",
        "Fornecedor": "TRIBUNAL DE JUSTICA DO ESTADO DE GOIAS",
        "ValorEmpenhado": "2.124,890",
        "CpfCnpjCredor": "02.292.266/0001-80",
        "Historico": "EMISSAO DE EMPENHO",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/centi":
            return httpx.Response(200, json=[empenho])
        # nenhuma secao multi_request (contratos/dispensas/licitacoes) existe
        # no portal de teste para trindade -> devolve vazio sempre.
        return httpx.Response(200, json={"k1": {"total": 0, "dados": []}})

    async with _client(httpx.MockTransport(handler)) as cli:
        res = await entidade.pesquisar_combinado(
            "trindade", nome="TRIBUNAL DE JUSTICA", cnpj="02292266000180", client=cli
        )

    despesas = next(g for g in res["grupos"] if g["secao"] == "despesas")
    assert despesas["total"] == 1
    assert set(despesas["itens"][0]["origem"]) == {"nome", "cnpj"}


async def test_pesquisar_combinado_propaga_truncamento_da_varredura(monkeypatch):
    """Varredura por CNPJ bate o teto de paginas antes de ver todos os
    registros -- `truncado`/`total_portal_cnpj` tem que chegar ao grupo e
    virar aviso, do jeito que `pesquisar()` ja faz (F2 da revisao P1)."""
    monkeypatch.setattr(entidade, "_PAGE", 1)
    monkeypatch.setattr(entidade, "_MAX_PAGINAS", 2)  # teto = 2 registros

    async with _client(make_portal()) as cli:
        res = await entidade.pesquisar_combinado(
            "senadorcanedo", cnpj="45.160.810/0001-43", client=cli
        )

    grupos = {g["secao"]: g for g in res["grupos"]}
    contratos = grupos["contratos"]
    assert contratos["truncado"] is True
    assert contratos["total_portal_cnpj"] == 3  # _CONTRATOS tem 3 linhas no total
    # so 1 dos 2 contratos da FL CONSTRUTORA foi visto antes do teto de paginas.
    assert contratos["total"] == 1
    assert any("truncada" in a and "contratos" in a for a in res["avisos"])
