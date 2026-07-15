"""Smoke tests da API de casos (P2). Sem rede: `busca_go.api.PESQUISAR_FN` e
stubado para simular a busca por entidade sem bater no portal.

Usa um `data/casos.db` ISOLADO por teste (`tmp_path`) -- nunca o banco real
do dev, e nunca compartilhado entre testes (o servidor de verdade e um
processo unico; um DB real compartilhado entre execucoes concorrentes de
teste faria a recuperacao de jobs presos (`recuperar_jobs_interrompidos`,
disparada no lifespan de CADA `TestClient`) marcar como 'interrompida' um
job de outro teste/processo ainda rodando de verdade)."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

import busca_go.api as api_module
import busca_go.nucleo.casos as casos_module
from busca_go.api import app
from busca_go.db import DB
from busca_go.nucleo import evidencia as evidencia_module


@pytest.fixture
def client(tmp_path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    banco_teste = DB(db_path=tmp_path / "casos-teste.db")
    monkeypatch.setattr(casos_module, "default_db", lambda: banco_teste)
    monkeypatch.setattr(evidencia_module.settings, "DATA_DIR", tmp_path)
    with TestClient(app) as c:
        yield c


def test_criar_listar_e_obter_caso(client: TestClient):
    r = client.post(
        "/api/casos",
        json={
            "titulo": "Caso de teste",
            "tipo": "livre",
            "alvos": {"nome": "Fulano"},
            "municipios": ["trindade"],
        },
    )
    assert r.status_code == 200
    caso = r.json()
    caso_id = caso["id"]
    assert caso["itens"] == []

    r_lista = client.get("/api/casos")
    assert r_lista.status_code == 200
    assert any(c["id"] == caso_id for c in r_lista.json())

    r_obter = client.get(f"/api/casos/{caso_id}")
    assert r_obter.status_code == 200
    assert r_obter.json()["id"] == caso_id


def test_criar_caso_municipio_invalido_404(client: TestClient):
    r = client.post(
        "/api/casos",
        json={"titulo": "X", "tipo": "livre", "alvos": {}, "municipios": ["municipio-fantasma"]},
    )
    assert r.status_code == 404


def test_obter_caso_inexistente_404(client: TestClient):
    r = client.get("/api/casos/caso_nao_existe")
    assert r.status_code == 404


def test_sequencia_completa_pesquisar_e_poll(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    """POST /api/casos -> POST /api/casos/{id}/pesquisar -> poll /api/jobs/{job_id}
    ate 'concluida' -> GET /api/casos/{id} lista os itens persistidos."""

    async def _fake_pesquisar(slug, q, ano=None, mes=None, client=None):
        return {
            "tipo": "cnpj",
            "termo": q,
            "municipio": {"slug": slug, "nome": slug},
            "grupos": [
                {
                    "secao": "contratos",
                    "modo": "server_side",
                    "total": 1,
                    "total_portal": 1,
                    "truncado": False,
                    "itens": [
                        {
                            "titulo": "0001/26",
                            "documento": q,
                            "valor": "R$ 1.000,00",
                            "data": "2026-01-01",
                            "ref_registro": {"id": "reg-1", "numero": "0001", "ano": "26"},
                            "raw": {},
                        }
                    ],
                }
            ],
            "avisos": [],
        }

    monkeypatch.setattr(api_module, "PESQUISAR_FN", _fake_pesquisar)

    r_caso = client.post(
        "/api/casos",
        json={
            "titulo": "Sequencia HTTP",
            "tipo": "dispensa_advocacia",
            "alvos": {"cnpj": "02292266000180"},
            "municipios": ["trindade"],
        },
    )
    assert r_caso.status_code == 200
    caso_id = r_caso.json()["id"]

    r_job = client.post(f"/api/casos/{caso_id}/pesquisar", json={})
    assert r_job.status_code == 200
    job_id = r_job.json()["job_id"]

    status = None
    limite = time.time() + 5
    while time.time() < limite:
        r_status = client.get(f"/api/jobs/{job_id}")
        assert r_status.status_code == 200
        status = r_status.json()["status"]
        if status == "concluida":
            break
        time.sleep(0.05)
    assert status == "concluida"

    r_final = client.get(f"/api/casos/{caso_id}")
    assert r_final.status_code == 200
    itens = r_final.json()["itens"]
    assert len(itens) == 1
    assert itens[0]["municipio"] == "trindade"
    assert itens[0]["secao"] == "contratos"


def test_pesquisar_caso_sem_alvo_400(client: TestClient):
    r_caso = client.post(
        "/api/casos",
        json={"titulo": "Sem alvo", "tipo": "livre", "alvos": {}, "municipios": ["trindade"]},
    )
    caso_id = r_caso.json()["id"]
    r = client.post(f"/api/casos/{caso_id}/pesquisar", json={})
    assert r.status_code == 400


def test_adicionar_item_e_anotacao(client: TestClient):
    r_caso = client.post(
        "/api/casos",
        json={"titulo": "Manual", "tipo": "livre", "alvos": {}, "municipios": ["trindade"]},
    )
    caso_id = r_caso.json()["id"]

    r_item = client.post(
        f"/api/casos/{caso_id}/itens",
        json={"municipio": "trindade", "secao": "contratos", "item": {"titulo": "Anexado a mao", "raw": {}}},
    )
    assert r_item.status_code == 200
    item_id = r_item.json()["item_id"]

    r_anotacao = client.post(
        f"/api/casos/{caso_id}/anotacoes",
        json={"item_id": item_id, "tag": "suspeito", "texto": "Conferir"},
    )
    assert r_anotacao.status_code == 200

    r_obter = client.get(f"/api/casos/{caso_id}")
    dados = r_obter.json()
    assert len(dados["itens"]) == 1
    assert len(dados["anotacoes"]) == 1


def test_job_inexistente_404(client: TestClient):
    r = client.get("/api/jobs/job_nao_existe")
    assert r.status_code == 404


def test_anotacao_com_item_id_inexistente_404(client: TestClient):
    """Review R2 F-01: item_id inexistente devolvia 500 (IntegrityError de FK
    nao tratado) em vez de 404."""
    r_caso = client.post(
        "/api/casos",
        json={"titulo": "Anotacao invalida", "tipo": "livre", "alvos": {}, "municipios": ["trindade"]},
    )
    caso_id = r_caso.json()["id"]

    r = client.post(
        f"/api/casos/{caso_id}/anotacoes",
        json={"item_id": "it_nao_existe", "tag": "x", "texto": "..."},
    )
    assert r.status_code == 404


def test_item_com_municipio_invalido_404(client: TestClient):
    """Review R2 F-02: município fictício não era validado em POST .../itens
    (inconsistente com POST /api/casos e /pesquisar, que já validam)."""
    r_caso = client.post(
        "/api/casos",
        json={"titulo": "Item municipio invalido", "tipo": "livre", "alvos": {}, "municipios": ["trindade"]},
    )
    caso_id = r_caso.json()["id"]

    r = client.post(
        f"/api/casos/{caso_id}/itens",
        json={"municipio": "marte", "secao": "contratos", "item": {"titulo": "X", "raw": {}}},
    )
    assert r.status_code == 404
