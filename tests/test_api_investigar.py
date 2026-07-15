"""Smoke tests do endpoint `POST /api/casos/{id}/investigar` (P4). Sem rede:
`busca_go.agente.cabeca.investigar` e stubado -- o endpoint so precisa provar
que dispara o job (mesma infra `buscas`/`GET /api/jobs/{id}` do P2) e que
recusa sem `OPENROUTER_API_KEY` configurada."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

import busca_go.api as api_module
import busca_go.nucleo.casos as casos_module
from busca_go.agente import cabeca as cabeca_module
from busca_go.agente.openrouter import CustoAcumulado
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


def _criar_caso(client: TestClient) -> str:
    r = client.post(
        "/api/casos",
        json={"titulo": "Investigar via agente", "tipo": "livre", "alvos": {"cnpj": "02292266000180"}, "municipios": ["trindade"]},
    )
    assert r.status_code == 200
    return r.json()["id"]


def test_investigar_sem_chave_openrouter_400(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(api_module.settings, "OPENROUTER_API_KEY", None)
    caso_id = _criar_caso(client)
    r = client.post(f"/api/casos/{caso_id}/investigar", json={})
    assert r.status_code == 400
    assert "OPENROUTER_API_KEY" in r.json()["detail"]


def test_investigar_caso_inexistente_404(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(api_module.settings, "OPENROUTER_API_KEY", "chave-teste")
    r = client.post("/api/casos/caso_fantasma/investigar", json={})
    assert r.status_code == 404


def test_sequencia_completa_investigar_e_poll(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    """POST /api/casos/{id}/investigar -> poll /api/jobs/{job_id} ate 'concluida'."""
    monkeypatch.setattr(api_module.settings, "OPENROUTER_API_KEY", "chave-teste")

    async def _fake_investigar(caso_id, descricao, **kwargs):
        return cabeca_module.ResultadoInvestigacao(
            caso_id=caso_id,
            subtarefas_executadas=[],
            lacunas=[],
            relatorio_md="# Dossie fake",
            relatorio_path="/tmp/relatorio.md",
            custo=CustoAcumulado(tokens_prompt=10, tokens_completion=5, custo_usd=0.0001, chamadas=2),
            teto_atingido=False,
        )

    monkeypatch.setattr(cabeca_module, "investigar", _fake_investigar)

    caso_id = _criar_caso(client)
    r_job = client.post(f"/api/casos/{caso_id}/investigar", json={"descricao": "Investigar CNPJ X em Trindade"})
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

    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["resultado_resumo"]["relatorio_path"] == "/tmp/relatorio.md"
    assert job["resultado_resumo"]["tokens_total"] == 15
    assert job["parametros"]["tipo"] == "investigacao"


def test_investigar_job_erro_quando_agente_falha(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(api_module.settings, "OPENROUTER_API_KEY", "chave-teste")

    async def _fake_falha(caso_id, descricao, **kwargs):
        raise RuntimeError("OpenRouter fora do ar")

    monkeypatch.setattr(cabeca_module, "investigar", _fake_falha)

    caso_id = _criar_caso(client)
    r_job = client.post(f"/api/casos/{caso_id}/investigar", json={})
    job_id = r_job.json()["job_id"]

    status = None
    limite = time.time() + 5
    while time.time() < limite:
        status = client.get(f"/api/jobs/{job_id}").json()["status"]
        if status == "erro":
            break
        time.sleep(0.05)
    assert status == "erro"


def test_investigar_falha_total_de_planejamento_vira_job_erro(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    """Review R4 F3: model-id invalido/OpenRouter fora do ar faz `planejar()`
    falhar por completo (0 subtarefas executadas, lacuna 'planejamento') --
    o job nao pode terminar como 'concluida' (enganaria quem so olha status)."""
    monkeypatch.setattr(api_module.settings, "OPENROUTER_API_KEY", "chave-teste")

    async def _fake_investigar_falha_total(caso_id, descricao, **kwargs):
        resultado = cabeca_module.ResultadoInvestigacao(caso_id=caso_id, relatorio_path="/tmp/relatorio.md")
        resultado.lacunas.append(
            cabeca_module.Lacuna("planejamento", "Planejamento da investigacao", "OpenRouter respondeu 400: model-id invalido")
        )
        return resultado

    monkeypatch.setattr(cabeca_module, "investigar", _fake_investigar_falha_total)

    caso_id = _criar_caso(client)
    r_job = client.post(f"/api/casos/{caso_id}/investigar", json={})
    job_id = r_job.json()["job_id"]

    status = None
    limite = time.time() + 5
    while time.time() < limite:
        status = client.get(f"/api/jobs/{job_id}").json()["status"]
        if status in ("erro", "concluida"):
            break
        time.sleep(0.05)
    assert status == "erro"
    resumo = client.get(f"/api/jobs/{job_id}").json()["resultado_resumo"]
    assert "model-id invalido" in resumo["erro"]


def test_investigar_usa_descricao_padrao_do_caso_quando_nao_informada(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(api_module.settings, "OPENROUTER_API_KEY", "chave-teste")
    capturado = {}

    async def _fake_investigar(caso_id, descricao, **kwargs):
        capturado["descricao"] = descricao
        return cabeca_module.ResultadoInvestigacao(caso_id=caso_id)

    monkeypatch.setattr(cabeca_module, "investigar", _fake_investigar)

    caso_id = _criar_caso(client)
    r_job = client.post(f"/api/casos/{caso_id}/investigar", json={})
    assert r_job.status_code == 200

    limite = time.time() + 5
    while time.time() < limite and "descricao" not in capturado:
        time.sleep(0.05)
    assert "Investigar via agente" in capturado["descricao"]
    assert "trindade" in capturado["descricao"]
