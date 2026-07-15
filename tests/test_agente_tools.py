"""Testes do dispatcher de tools do agente (`busca_go/agente/tools.py`):
validacao de argumentos (guardrail §6.2 #1) + persistencia no caso. Sem rede
(sempre monkeypatcha a funcao de `nucleo/*` que a tool chama)."""

from __future__ import annotations

import pytest

from busca_go.agente import tools
from busca_go.db import DB
from busca_go.nucleo import casos as casos_module
from busca_go.nucleo import centi, entidade, evidencia


@pytest.fixture
def caso_db(tmp_path, monkeypatch: pytest.MonkeyPatch) -> DB:
    banco = DB(db_path=tmp_path / "casos-teste.db")
    monkeypatch.setattr(casos_module, "default_db", lambda: banco)
    monkeypatch.setattr(evidencia.settings, "DATA_DIR", tmp_path)
    return banco


def _caso(banco: DB) -> str:
    caso = casos_module.criar_caso(
        titulo="Caso de teste", tipo="livre", alvos={"cnpj": "02292266000180"},
        municipios=["trindade"], db=banco,
    )
    return caso["id"]


# --------------------------------------------------------------------------- #
# Validacao de argumentos (guardrail §6.2 #1)
# --------------------------------------------------------------------------- #


async def test_municipio_invalido_vira_toolargumentoinvalido(caso_db):
    caso_id = _caso(caso_db)
    with pytest.raises(tools.ToolArgumentoInvalido):
        await tools.executar_tool("buscar_entidade", {"slug": "marte", "nome": "X"}, caso_id=caso_id)


async def test_cnpj_com_formato_invalido_vira_toolargumentoinvalido(caso_db):
    caso_id = _caso(caso_db)
    with pytest.raises(tools.ToolArgumentoInvalido):
        await tools.executar_tool("buscar_entidade", {"slug": "trindade", "cnpj": "123"}, caso_id=caso_id)


async def test_buscar_entidade_sem_nome_nem_cnpj_vira_toolargumentoinvalido(caso_db):
    caso_id = _caso(caso_db)
    with pytest.raises(tools.ToolArgumentoInvalido):
        await tools.executar_tool("buscar_entidade", {"slug": "trindade"}, caso_id=caso_id)


async def test_tool_desconhecida_vira_toolargumentoinvalido(caso_db):
    caso_id = _caso(caso_db)
    with pytest.raises(tools.ToolArgumentoInvalido):
        await tools.executar_tool("tool_que_nao_existe", {}, caso_id=caso_id)


async def test_args_nao_dict_vira_toolargumentoinvalido(caso_db):
    caso_id = _caso(caso_db)
    with pytest.raises(tools.ToolArgumentoInvalido):
        await tools.executar_tool("buscar_entidade", "nao-e-dict", caso_id=caso_id)  # type: ignore[arg-type]


async def test_buscar_despesas_centi_fora_dos_municipios_centi_vira_toolargumentoinvalido(caso_db):
    caso_id = _caso(caso_db)
    with pytest.raises(tools.ToolArgumentoInvalido):
        await tools.executar_tool(
            "buscar_despesas_centi", {"slug": "senadorcanedo", "credor": "X"}, caso_id=caso_id
        )


async def test_baixar_evidencias_sem_item_id_vira_toolargumentoinvalido(caso_db):
    caso_id = _caso(caso_db)
    with pytest.raises(tools.ToolArgumentoInvalido):
        await tools.executar_tool("baixar_evidencias_registro", {}, caso_id=caso_id)


async def test_screenshot_folha_sem_ano_mes_vira_toolargumentoinvalido(caso_db):
    caso_id = _caso(caso_db)
    with pytest.raises(tools.ToolArgumentoInvalido):
        await tools.executar_tool(
            "capturar_screenshot_folha", {"slug": "trindade", "nome": "Maria"}, caso_id=caso_id
        )


# --------------------------------------------------------------------------- #
# buscar_entidade -- persiste itens no caso, devolve versao enxuta
# --------------------------------------------------------------------------- #


async def test_buscar_entidade_persiste_itens_e_devolve_enxuto(caso_db, monkeypatch: pytest.MonkeyPatch):
    caso_id = _caso(caso_db)

    async def _fake_pesquisar_combinado(slug, nome=None, cnpj=None, client=None):
        assert slug == "trindade"
        return {
            "grupos": [
                {
                    "secao": "contratos",
                    "itens": [
                        {
                            "titulo": "0001/26",
                            "documento": cnpj,
                            "valor": "R$ 1.000,00",
                            "data": "2026-01-01",
                            "ref_registro": {"id": "reg-1", "numero": "0001", "ano": "26"},
                            "raw": {"campo_interno": "nao deve vazar pro worker"},
                            "origem": ["cnpj"],
                        }
                    ],
                }
            ],
            "avisos": ["aviso de teste"],
        }

    monkeypatch.setattr(entidade, "pesquisar_combinado", _fake_pesquisar_combinado)

    resultado = await tools.executar_tool(
        "buscar_entidade", {"slug": "trindade", "cnpj": "02.292.266/0001-80"}, caso_id=caso_id
    )

    assert resultado["avisos"] == ["aviso de teste"]
    grupo = resultado["grupos"][0]
    assert grupo["secao"] == "contratos"
    item = grupo["itens"][0]
    assert item["titulo"] == "0001/26"
    assert item["ref_registro"] == {"id": "reg-1", "numero": "0001", "ano": "26"}
    assert "raw" not in item  # versao enxuta -- nao reenvia payload bruto pro modelo barato
    assert item["item_id"].startswith("it_")

    persistido = casos_module.obter_item(item["item_id"], db=caso_db)
    assert persistido is not None
    assert persistido["municipio"] == "trindade"
    assert persistido["secao"] == "contratos"


async def test_buscar_entidade_portalerror_vira_toolexecucaoerror(caso_db, monkeypatch: pytest.MonkeyPatch):
    caso_id = _caso(caso_db)

    async def _fake_falha(slug, nome=None, cnpj=None, client=None):
        raise entidade.PortalError("portal fora do ar")

    monkeypatch.setattr(entidade, "pesquisar_combinado", _fake_falha)
    with pytest.raises(tools.ToolExecucaoError):
        await tools.executar_tool("buscar_entidade", {"slug": "trindade", "nome": "X"}, caso_id=caso_id)


# --------------------------------------------------------------------------- #
# buscar_despesas_centi
# --------------------------------------------------------------------------- #


async def test_buscar_despesas_centi_persiste_itens(caso_db, monkeypatch: pytest.MonkeyPatch):
    caso_id = _caso(caso_db)

    async def _fake_buscar_despesas(client, url_base, *, cpf_cnpj=None, credor=None, data_inicio=None, data_fim=None):
        assert cpf_cnpj == "02292266000180"
        return [
            {
                "titulo": "203152",
                "fornecedor": "TJGO",
                "documento": cpf_cnpj,
                "valor": "2.124,89",
                "data": "14/07/2026",
                "tem_aditivo": False,
                "ref_registro": {"id": "203152", "numero": "203152", "ano": ""},
                "tem_anexos": False,
                "raw": {},
            }
        ]

    monkeypatch.setattr(centi, "buscar_despesas", _fake_buscar_despesas)

    resultado = await tools.executar_tool(
        "buscar_despesas_centi", {"slug": "trindade", "cpf_cnpj": "02.292.266/0001-80"}, caso_id=caso_id
    )
    assert resultado["grupos"][0]["secao"] == "despesas"
    item = resultado["grupos"][0]["itens"][0]
    assert item["item_id"].startswith("it_")
    assert casos_module.obter_item(item["item_id"], db=caso_db) is not None


async def test_buscar_despesas_centi_filtra_itens_fora_do_periodo(caso_db, monkeypatch: pytest.MonkeyPatch):
    """F7: empenhos de anos fora do periodo pedido pelo usuario NAO sao
    persistidos -- filtro deterministico em `_persistir_grupos`, nao depende
    do worker lembrar de filtrar."""
    caso_id = _caso(caso_db)

    async def _fake_buscar_despesas(client, url_base, *, cpf_cnpj=None, credor=None, data_inicio=None, data_fim=None):
        datas = ["13/03/2015", "10/05/2024", "22/11/2025", "01/01/2026"]
        return [
            {
                "titulo": f"emp-{i}",
                "documento": cpf_cnpj,
                "valor": "100,00",
                "data": data,
                "ref_registro": {"id": f"emp-{i}", "numero": f"emp-{i}", "ano": ""},
                "raw": {},
            }
            for i, data in enumerate(datas)
        ]

    monkeypatch.setattr(centi, "buscar_despesas", _fake_buscar_despesas)

    resultado = await tools.executar_tool(
        "buscar_despesas_centi",
        {"slug": "trindade", "cpf_cnpj": "02.292.266/0001-80"},
        caso_id=caso_id,
        periodo=(2024, 2025),
    )
    itens = resultado["grupos"][0]["itens"]
    assert [i["data"] for i in itens] == ["10/05/2024", "22/11/2025"]
    assert any("2 item" in a and "2024-2025" in a for a in resultado["avisos"])
    for item in itens:
        assert casos_module.obter_item(item["item_id"], db=caso_db) is not None


async def test_buscar_despesas_centi_mantem_item_sem_ano_detectavel(caso_db, monkeypatch: pytest.MonkeyPatch):
    """Erra para o lado de MANTER: item cujo ano nao da pra extrair de forma
    confiavel nao e descartado so por causa do filtro de periodo (evita
    sumir com achado real por falha de parsing de data)."""
    caso_id = _caso(caso_db)

    async def _fake_buscar_despesas(client, url_base, *, cpf_cnpj=None, credor=None, data_inicio=None, data_fim=None):
        return [
            {
                "titulo": "emp-sem-data",
                "documento": cpf_cnpj,
                "valor": "100,00",
                "data": "",
                "ref_registro": {"id": "emp-x", "numero": "emp-x", "ano": ""},
                "raw": {},
            }
        ]

    monkeypatch.setattr(centi, "buscar_despesas", _fake_buscar_despesas)

    resultado = await tools.executar_tool(
        "buscar_despesas_centi",
        {"slug": "trindade", "cpf_cnpj": "02.292.266/0001-80"},
        caso_id=caso_id,
        periodo=(2024, 2025),
    )
    assert len(resultado["grupos"][0]["itens"]) == 1


async def test_buscar_despesas_centi_falha_vira_toolexecucaoerror(caso_db, monkeypatch: pytest.MonkeyPatch):
    caso_id = _caso(caso_db)

    async def _fake_falha(client, url_base, **kwargs):
        raise centi.PortalError("Centi fora do ar")

    monkeypatch.setattr(centi, "buscar_despesas", _fake_falha)
    with pytest.raises(tools.ToolExecucaoError):
        await tools.executar_tool(
            "buscar_despesas_centi", {"slug": "trindade", "credor": "X"}, caso_id=caso_id
        )


# --------------------------------------------------------------------------- #
# buscar_folha
# --------------------------------------------------------------------------- #


async def test_buscar_folha_persiste_apenas_grupo_folha(caso_db, monkeypatch: pytest.MonkeyPatch):
    caso_id = _caso(caso_db)

    async def _fake_pesquisar(slug, q, ano=None, mes=None, client=None):
        return {
            "tipo": "termo",
            "termo": q,
            "municipio": {"slug": slug, "nome": slug},
            "grupos": [
                {"secao": "contratos", "itens": [{"titulo": "nao deveria ser persistido pela busca de folha"}]},
                {
                    "secao": "folha",
                    "itens": [
                        {
                            "matricula": "123",
                            "nome": q,
                            "ano": str(ano),
                            "mes": str(mes),
                            "liquido": "3.500,00",
                            "raw": {},
                        }
                    ],
                },
            ],
            "avisos": [],
        }

    monkeypatch.setattr(entidade, "pesquisar", _fake_pesquisar)

    resultado = await tools.executar_tool(
        "buscar_folha", {"slug": "trindade", "nome": "Maria", "ano": 2024, "mes": 6}, caso_id=caso_id
    )
    assert len(resultado["grupos"]) == 1
    assert resultado["grupos"][0]["secao"] == "folha"
    item_id = resultado["grupos"][0]["itens"][0]["item_id"]
    persistido = casos_module.obter_item(item_id, db=caso_db)
    assert persistido["secao"] == "folha"


async def test_buscar_folha_sem_registro_avisa(caso_db, monkeypatch: pytest.MonkeyPatch):
    caso_id = _caso(caso_db)

    async def _fake_pesquisar(slug, q, ano=None, mes=None, client=None):
        return {"tipo": "termo", "termo": q, "municipio": {"slug": slug, "nome": slug}, "grupos": [], "avisos": []}

    monkeypatch.setattr(entidade, "pesquisar", _fake_pesquisar)
    resultado = await tools.executar_tool(
        "buscar_folha", {"slug": "trindade", "nome": "Ninguem"}, caso_id=caso_id
    )
    assert resultado["grupos"] == []
    assert any("Nenhum registro de folha" in a for a in resultado["avisos"])


# --------------------------------------------------------------------------- #
# baixar_evidencias_registro (F1: resolve o registro completo a partir do
# item_id ja persistido -- o worker LLM NUNCA monta 'registro' na mao)
# --------------------------------------------------------------------------- #


def _item_contrato_completo(banco: DB, caso_id: str) -> str:
    return casos_module.adicionar_item(
        caso_id, "trindade", "contratos",
        {"titulo": "016/2017", "ref_registro": {"id": "517", "numero": "002", "ano": "2017"}, "raw": {}},
        db=banco,
    )


async def test_baixar_evidencias_por_item_id_resolve_registro_completo(caso_db, monkeypatch: pytest.MonkeyPatch):
    caso_id = _caso(caso_db)
    item_id = _item_contrato_completo(caso_db, caso_id)

    async def _fake_baixar(caso_id_arg, slug, secao, registro, item_id=None, client=None, db=None):
        assert caso_id_arg == caso_id
        assert slug == "trindade" and secao == "contratos"
        assert registro == {"id": "517", "numero": "002", "ano": "2017"}
        resultado = evidencia.ResultadoEvidencias()
        resultado.baixados = [{"evidencia_id": "ev_000001"}, {"evidencia_id": "ev_000002"}]
        resultado.teto_atingido = False
        return resultado

    monkeypatch.setattr(evidencia, "baixar_evidencias_registro", _fake_baixar)

    resultado = await tools.executar_tool(
        "baixar_evidencias_registro", {"item_id": item_id}, caso_id=caso_id
    )
    assert resultado["evidencia_ids"] == ["ev_000001", "ev_000002"]
    assert resultado["falhas"] == []
    assert resultado["pendentes"] == 0
    assert resultado["teto_atingido"] is False


async def test_baixar_evidencias_item_id_inexistente_vira_toolargumentoinvalido(caso_db):
    caso_id = _caso(caso_db)
    with pytest.raises(tools.ToolArgumentoInvalido):
        await tools.executar_tool("baixar_evidencias_registro", {"item_id": "it_nao_existe"}, caso_id=caso_id)


async def test_baixar_evidencias_item_id_de_outro_caso_vira_toolargumentoinvalido(caso_db):
    caso_id_a = _caso(caso_db)
    caso_id_b = casos_module.criar_caso(
        titulo="Outro caso", tipo="livre", alvos={}, municipios=["trindade"], db=caso_db
    )["id"]
    item_id = _item_contrato_completo(caso_db, caso_id_a)
    with pytest.raises(tools.ToolArgumentoInvalido):
        await tools.executar_tool("baixar_evidencias_registro", {"item_id": item_id}, caso_id=caso_id_b)


async def test_baixar_evidencias_item_de_secao_nao_documental_vira_toolargumentoinvalido(caso_db):
    """F1(b): id de empenho (secao 'despesas') nao e registro de licitacao --
    rejeita com erro claro em vez de tentar baixar (e voltar vazio)."""
    caso_id = _caso(caso_db)
    item_id = casos_module.adicionar_item(
        caso_id, "trindade", "despesas",
        {"titulo": "178108", "ref_registro": {"id": "178108", "numero": "178108", "ano": ""}, "raw": {}},
        db=caso_db,
    )
    with pytest.raises(tools.ToolArgumentoInvalido, match="despesas"):
        await tools.executar_tool("baixar_evidencias_registro", {"item_id": item_id}, caso_id=caso_id)


async def test_baixar_evidencias_item_folha_vira_toolargumentoinvalido(caso_db):
    caso_id = _caso(caso_db)
    item_id = casos_module.adicionar_item(
        caso_id, "trindade", "folha",
        {"matricula": "123", "nome": "X", "ano": "2024", "mes": "6", "raw": {}},
        db=caso_db,
    )
    with pytest.raises(tools.ToolArgumentoInvalido):
        await tools.executar_tool("baixar_evidencias_registro", {"item_id": item_id}, caso_id=caso_id)


async def test_baixar_evidencias_item_com_registro_incompleto_vira_toolargumentoinvalido_sem_chamar_evidencia(
    caso_db, monkeypatch: pytest.MonkeyPatch
):
    """F1(c): registro incompleto (sem 'numero') nunca chega na camada de
    evidencia -- vira is_error aqui mesmo, nunca 'baixados:[] sucesso vazio'."""
    caso_id = _caso(caso_db)
    item_id = casos_module.adicionar_item(
        caso_id, "trindade", "contratos",
        {"titulo": "X", "ref_registro": {"id": "517"}, "raw": {}},
        db=caso_db,
    )

    async def _nao_deveria_ser_chamado(*args, **kwargs):
        raise AssertionError("registro incompleto nao deveria chegar na camada de evidencia")

    monkeypatch.setattr(evidencia, "baixar_evidencias_registro", _nao_deveria_ser_chamado)
    with pytest.raises(tools.ToolArgumentoInvalido):
        await tools.executar_tool("baixar_evidencias_registro", {"item_id": item_id}, caso_id=caso_id)


async def test_baixar_evidencias_secao_indisponivel_no_municipio_vira_argumento(
    caso_db, monkeypatch: pytest.MonkeyPatch
):
    caso_id = _caso(caso_db)
    item_id = _item_contrato_completo(caso_db, caso_id)

    from busca_go.nucleo.routes import SecaoIndisponivel

    async def _fake_baixar(*args, **kwargs):
        raise SecaoIndisponivel("secao inexistente nesse municipio")

    monkeypatch.setattr(evidencia, "baixar_evidencias_registro", _fake_baixar)
    with pytest.raises(tools.ToolArgumentoInvalido):
        await tools.executar_tool("baixar_evidencias_registro", {"item_id": item_id}, caso_id=caso_id)


# --------------------------------------------------------------------------- #
# capturar_screenshot_folha
# --------------------------------------------------------------------------- #


async def test_capturar_screenshot_folha_junta_evidencia_relacionada(
    caso_db, monkeypatch: pytest.MonkeyPatch
):
    caso_id = _caso(caso_db)

    async def _fake_captura(caso_id_arg, slug, nome, ano, mes, matricula=None, item_id=None, **kwargs):
        return evidencia.EvidenciaFolha(
            png={"evidencia_id": "ev_000010"},
            json_valores={"itens": []},
            avisos=["aviso periodo padrao"],
        )

    def _fake_manifesto(caso_id_arg):
        return [
            {"evidencia_id": "ev_000010", "tipo": "screenshot"},
            {"evidencia_id": "ev_000011", "tipo": "json", "evidencia_relacionada": "ev_000010"},
        ]

    monkeypatch.setattr(evidencia, "capturar_screenshot_folha", _fake_captura)
    monkeypatch.setattr(evidencia, "ler_manifesto", _fake_manifesto)

    resultado = await tools.executar_tool(
        "capturar_screenshot_folha",
        {"slug": "trindade", "nome": "Maria", "ano": 2024, "mes": 6},
        caso_id=caso_id,
    )
    assert resultado["evidencia_ids"] == ["ev_000010", "ev_000011"]
    assert resultado["avisos"] == ["aviso periodo padrao"]
