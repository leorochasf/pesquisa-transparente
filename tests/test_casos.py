"""Testes do repositorio de casos (`busca_go/nucleo/casos.py`) e do banco
(`busca_go/db.py`). Cada teste usa um DB SQLite isolado em `tmp_path` (nunca
toca `data/casos.db` de verdade)."""

from __future__ import annotations

import pytest

from busca_go.db import DB
from busca_go.nucleo import casos


@pytest.fixture
def db(tmp_path) -> DB:
    return DB(db_path=tmp_path / "casos-teste.db")


# --------------------------------------------------------------------------- #
# casos
# --------------------------------------------------------------------------- #


def test_criar_e_obter_caso(db: DB):
    caso = casos.criar_caso(
        titulo="Escritório X — dispensa",
        tipo="dispensa_advocacia",
        alvos={"nome": "Escritorio X", "cnpj": "02292266000180"},
        municipios=["senadorcanedo", "trindade"],
        db=db,
    )
    assert caso["id"].startswith("caso_")
    assert caso["titulo"] == "Escritório X — dispensa"
    assert caso["itens"] == []
    assert caso["evidencias"] == []
    assert caso["anotacoes"] == []

    obtido = casos.obter_caso(caso["id"], db=db)
    assert obtido is not None
    assert obtido["alvos"]["cnpj"] == "02292266000180"
    assert obtido["municipios"] == ["senadorcanedo", "trindade"]


def test_obter_caso_inexistente_retorna_none(db: DB):
    assert casos.obter_caso("caso_inexistente", db=db) is None


def test_listar_casos_ordem_mais_recente_primeiro(db: DB):
    c1 = casos.criar_caso(titulo="Primeiro", tipo="livre", alvos={}, municipios=["trindade"], db=db)
    c2 = casos.criar_caso(titulo="Segundo", tipo="livre", alvos={}, municipios=["trindade"], db=db)
    listagem = casos.listar_casos(db=db)
    ids = [c["id"] for c in listagem]
    assert ids[0] == c2["id"]
    assert c1["id"] in ids


# --------------------------------------------------------------------------- #
# itens (agregacao + dedup)
# --------------------------------------------------------------------------- #


def test_adicionar_itens_da_busca_persiste(db: DB):
    caso = casos.criar_caso(titulo="Caso itens", tipo="livre", alvos={}, municipios=["trindade"], db=db)
    itens = [
        {
            "titulo": "0343/26",
            "documento": "02292266000180",
            "valor": "R$ 10.000,00",
            "data": "2026-01-10",
            "ref_registro": {"id": "abc123", "numero": "0343", "ano": "26"},
            "raw": {},
        }
    ]
    novos = casos.adicionar_itens_da_busca(caso["id"], "trindade", "contratos", itens, db=db)
    assert novos == 1

    obtido = casos.obter_caso(caso["id"], db=db)
    assert len(obtido["itens"]) == 1
    item = obtido["itens"][0]
    assert item["municipio"] == "trindade"
    assert item["secao"] == "contratos"
    assert item["titulo"] == "0343/26"
    assert item["ref_registro"] == {"id": "abc123", "numero": "0343", "ano": "26"}


def test_adicionar_itens_da_busca_deduplica_por_ref_registro(db: DB):
    """Reexecutar a mesma busca (mesmo ref_registro.id) nao deve duplicar a linha."""
    caso = casos.criar_caso(titulo="Caso dedup", tipo="livre", alvos={}, municipios=["trindade"], db=db)
    item = {
        "titulo": "0343/26",
        "documento": "02292266000180",
        "valor": "R$ 10.000,00",
        "data": "2026-01-10",
        "ref_registro": {"id": "abc123", "numero": "0343", "ano": "26"},
        "raw": {},
    }
    casos.adicionar_itens_da_busca(caso["id"], "trindade", "contratos", [item], db=db)
    casos.adicionar_itens_da_busca(caso["id"], "trindade", "contratos", [item], db=db)

    obtido = casos.obter_caso(caso["id"], db=db)
    assert len(obtido["itens"]) == 1


def test_item_sem_ref_registro_persiste(db: DB):
    caso = casos.criar_caso(titulo="Caso fallback", tipo="livre", alvos={}, municipios=["trindade"], db=db)
    item = {"titulo": "Contrato sem id", "valor": "R$ 500,00", "data": "2026-02-01", "raw": {}}
    casos.adicionar_itens_da_busca(caso["id"], "trindade", "contratos", [item], db=db)
    obtido = casos.obter_caso(caso["id"], db=db)
    assert len(obtido["itens"]) == 1


def test_itens_sem_ref_registro_nao_colapsam_entre_si(db: DB):
    """Review R2 F-04: sem `ref_registro.id`, dois achados NAO podem virar
    uma linha so, mesmo que titulo/data/valor coincidam por acaso (o
    fallback antigo (titulo,data,valor) colapsava silenciosamente e perdia
    o `raw_json` de um dos dois -- inaceitavel num app cuja tese e lastro)."""
    caso = casos.criar_caso(titulo="Caso sem colapso", tipo="livre", alvos={}, municipios=["trindade"], db=db)
    # "raw_json" grava o item inteiro (nao so o campo "raw"); "fornecedor" no
    # topo do item e o jeito de distinguir os dois achados apos persistidos.
    item_a = {"titulo": "Serviços diversos", "valor": "R$ 500,00", "data": "2026-02-01", "fornecedor": "A"}
    item_b = {"titulo": "Serviços diversos", "valor": "R$ 500,00", "data": "2026-02-01", "fornecedor": "B"}
    casos.adicionar_itens_da_busca(caso["id"], "trindade", "contratos", [item_a], db=db)
    casos.adicionar_itens_da_busca(caso["id"], "trindade", "contratos", [item_b], db=db)

    obtido = casos.obter_caso(caso["id"], db=db)
    assert len(obtido["itens"]) == 2
    fornecedores = {i["raw"]["fornecedor"] for i in obtido["itens"]}
    assert fornecedores == {"A", "B"}


def test_item_folha_usa_matricula_periodo_como_chave(db: DB):
    caso = casos.criar_caso(titulo="Caso folha", tipo="dano_erario_folha", alvos={}, municipios=["trindade"], db=db)
    item_folha = {
        "matricula": "12345",
        "nome": "Maria Silva",
        "ano": "2024",
        "mes": "03",
        "liquido": "R$ 3.000,00",
        "raw": {},
    }
    casos.adicionar_itens_da_busca(caso["id"], "trindade", "folha", [item_folha], db=db)
    obtido = casos.obter_caso(caso["id"], db=db)
    assert len(obtido["itens"]) == 1
    assert obtido["itens"][0]["documento"] == "12345"
    assert obtido["itens"][0]["valor"] == "R$ 3.000,00"


# --------------------------------------------------------------------------- #
# anotacoes
# --------------------------------------------------------------------------- #


def test_adicionar_anotacao_do_caso_e_de_item(db: DB):
    caso = casos.criar_caso(titulo="Caso anotado", tipo="livre", alvos={}, municipios=["trindade"], db=db)
    casos.adicionar_itens_da_busca(
        caso["id"], "trindade", "contratos", [{"titulo": "X", "raw": {}}], db=db
    )
    item_id = casos.obter_caso(caso["id"], db=db)["itens"][0]["id"]

    an_caso = casos.adicionar_anotacao(caso["id"], None, "suspeito", "Ver isso com calma", db=db)
    an_item = casos.adicionar_anotacao(caso["id"], item_id, "sobrepreco?", "Valor destoante", db=db)

    obtido = casos.obter_caso(caso["id"], db=db)
    assert len(obtido["anotacoes"]) == 2
    ids = {a["id"] for a in obtido["anotacoes"]}
    assert an_caso["id"] in ids
    assert an_item["id"] in ids


# --------------------------------------------------------------------------- #
# buscas (jobs) — status/progresso + recuperacao no boot
# --------------------------------------------------------------------------- #


def test_ciclo_de_vida_do_job(db: DB):
    caso = casos.criar_caso(titulo="Caso job", tipo="livre", alvos={}, municipios=["trindade"], db=db)
    job_id = casos.criar_busca(caso["id"], {"q": "x", "municipios": ["trindade"]}, db=db)

    job = casos.obter_busca(job_id, db=db)
    assert job["status"] == "fila"
    assert job["concluida_em"] is None

    casos.marcar_busca_status(job_id, "rodando", progresso={"municipios_feitos": 0}, db=db)
    job = casos.obter_busca(job_id, db=db)
    assert job["status"] == "rodando"
    assert job["progresso"] == {"municipios_feitos": 0}
    assert job["concluida_em"] is None

    casos.marcar_busca_status(
        job_id, "concluida", resultado_resumo={"total_itens": 3, "avisos": []}, db=db
    )
    job = casos.obter_busca(job_id, db=db)
    assert job["status"] == "concluida"
    assert job["resultado_resumo"]["total_itens"] == 3
    assert job["concluida_em"] is not None


def test_obter_busca_inexistente_retorna_none(db: DB):
    assert casos.obter_busca("job_inexistente", db=db) is None


def test_recuperar_jobs_interrompidos_marca_fila_e_rodando(db: DB):
    caso = casos.criar_caso(titulo="Caso crash", tipo="livre", alvos={}, municipios=["trindade"], db=db)
    job_fila = casos.criar_busca(caso["id"], {"q": "x"}, db=db)
    job_rodando = casos.criar_busca(caso["id"], {"q": "y"}, db=db)
    job_concluido = casos.criar_busca(caso["id"], {"q": "z"}, db=db)

    casos.marcar_busca_status(job_rodando, "rodando", db=db)
    casos.marcar_busca_status(job_concluido, "concluida", resultado_resumo={"total_itens": 0}, db=db)

    marcados = casos.recuperar_jobs_interrompidos(db=db)
    assert marcados == 2  # fila + rodando; concluida nao mexe

    assert casos.obter_busca(job_fila, db=db)["status"] == "interrompida"
    assert casos.obter_busca(job_rodando, db=db)["status"] == "interrompida"
    assert casos.obter_busca(job_concluido, db=db)["status"] == "concluida"


def test_db_sobrevive_a_reabertura(tmp_path):
    """Simula 'matar e subir o servidor': reabrir o mesmo arquivo preserva os dados."""
    caminho = tmp_path / "persistente.db"
    db1 = DB(db_path=caminho)
    caso = casos.criar_caso(titulo="Persistente", tipo="livre", alvos={}, municipios=["trindade"], db=db1)
    job_id = casos.criar_busca(caso["id"], {"q": "x"}, db=db1)
    casos.marcar_busca_status(job_id, "rodando", db=db1)

    # "restart do processo": novo objeto DB sobre o mesmo arquivo.
    db2 = DB(db_path=caminho)
    assert casos.obter_caso(caso["id"], db=db2) is not None
    casos.recuperar_jobs_interrompidos(db=db2)
    assert casos.obter_busca(job_id, db=db2)["status"] == "interrompida"
