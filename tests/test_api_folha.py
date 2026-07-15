"""Smoke tests do endpoint `POST /api/casos/{id}/folha` (ACEIT-F5). Sem rede:
`busca_go.nucleo.evidencia.persistir_e_capturar_folha` e stubado -- o
endpoint so precisa provar que dispara o job (mesma infra `buscas`/
`GET /api/jobs/{id}` de P2/P4), persiste 1 item por competencia e encerra com
erro claro quando ha homonimo (nao continua as demais competencias)."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

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


def _criar_caso(client: TestClient) -> str:
    r = client.post(
        "/api/casos",
        json={
            "titulo": "Dano ao erário — folha",
            "tipo": "dano_erario_folha",
            "alvos": {"servidor": "Joana"},
            "municipios": ["senadorcanedo"],
        },
    )
    assert r.status_code == 200
    return r.json()["id"]


def _poll(client: TestClient, job_id: str, alvo: set[str] = frozenset({"concluida", "erro"})) -> str:
    status = None
    limite = time.time() + 5
    while time.time() < limite:
        status = client.get(f"/api/jobs/{job_id}").json()["status"]
        if status in alvo:
            break
        time.sleep(0.05)
    return status


def test_folha_caso_inexistente_404(client: TestClient):
    r = client.post(
        "/api/casos/caso_fantasma/folha",
        json={"municipio": "senadorcanedo", "servidor": "Joana", "competencias": [{"ano": 2025, "mes": 1}]},
    )
    assert r.status_code == 404


def test_folha_sem_competencias_400(client: TestClient):
    caso_id = _criar_caso(client)
    r = client.post(
        "/api/casos/{}/folha".format(caso_id),
        json={"municipio": "senadorcanedo", "servidor": "Joana", "competencias": []},
    )
    assert r.status_code == 400


def test_folha_mes_invalido_400(client: TestClient):
    caso_id = _criar_caso(client)
    r = client.post(
        f"/api/casos/{caso_id}/folha",
        json={"municipio": "senadorcanedo", "servidor": "Joana", "competencias": [{"ano": 2025, "mes": 13}]},
    )
    assert r.status_code == 400


def test_folha_municipio_inexistente_404(client: TestClient):
    caso_id = _criar_caso(client)
    r = client.post(
        f"/api/casos/{caso_id}/folha",
        json={"municipio": "goiania", "servidor": "Joana", "competencias": [{"ano": 2025, "mes": 1}]},
    )
    assert r.status_code == 404


def test_folha_num_passo_2_competencias_conclui_com_2_itens(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    """Criterio de pronto: 2 competencias -> job conclui -> 2 itens, cada um
    com item_id devolvido (a evidencia real e testada sem rede em
    test_evidencia.py -- aqui so a orquestracao do job)."""
    chamadas: list[dict] = []

    async def fake_persistir(caso_id, slug, nome, ano, mes, matricula=None, **kwargs):
        chamadas.append({"ano": ano, "mes": mes})
        return {
            "item_id": f"it_{ano}{mes:02d}",
            "item": {"nome": nome, "ano": ano, "mes": mes},
            "evidencia_png_id": "ev_x",
            "evidencia_json_id": "ev_y",
            "avisos": [],
        }

    monkeypatch.setattr(evidencia_module, "persistir_e_capturar_folha", fake_persistir)

    caso_id = _criar_caso(client)
    r_job = client.post(
        f"/api/casos/{caso_id}/folha",
        json={
            "municipio": "senadorcanedo",
            "servidor": "JOANA TESTE DA SILVA",
            "matricula": "90001",
            "competencias": [{"ano": 2025, "mes": 1}, {"ano": 2025, "mes": 3}],
        },
    )
    assert r_job.status_code == 200
    job_id = r_job.json()["job_id"]

    status = _poll(client, job_id)
    assert status == "concluida"
    job = client.get(f"/api/jobs/{job_id}").json()
    assert len(job["resultado_resumo"]["itens"]) == 2
    assert job["resultado_resumo"]["falhas"] == []
    assert len(chamadas) == 2


def test_folha_homonimo_ambiguo_encerra_job_com_erro_claro(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    """ACEIT-F5: EvidenciaAmbigua encerra o job imediatamente (nao continua
    as competencias restantes) com a mensagem de candidatos no resumo."""
    chamadas: list[dict] = []

    async def fake_persistir(caso_id, slug, nome, ano, mes, matricula=None, **kwargs):
        chamadas.append({"ano": ano, "mes": mes})
        raise evidencia_module.EvidenciaAmbigua(
            "'MARIA' casa com 2 servidores distintos -- candidatos: MARIA DA SILVA (matricula 111); "
            "MARIA DOS SANTOS (matricula 222)."
        )

    monkeypatch.setattr(evidencia_module, "persistir_e_capturar_folha", fake_persistir)

    caso_id = _criar_caso(client)
    r_job = client.post(
        f"/api/casos/{caso_id}/folha",
        json={
            "municipio": "senadorcanedo",
            "servidor": "MARIA",
            "competencias": [{"ano": 2025, "mes": 1}, {"ano": 2025, "mes": 2}],
        },
    )
    job_id = r_job.json()["job_id"]

    status = _poll(client, job_id)
    assert status == "erro"
    resumo = client.get(f"/api/jobs/{job_id}").json()["resultado_resumo"]
    assert "MARIA DA SILVA" in resumo["erro"] and "MARIA DOS SANTOS" in resumo["erro"]
    # parou na 1a competencia ambigua -- nao tentou a segunda.
    assert len(chamadas) == 1
