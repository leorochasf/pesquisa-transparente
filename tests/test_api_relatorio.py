"""Smoke test do endpoint `GET /api/casos/{id}/relatorio?formato=pdf` (W1):
responde o PDF de fato (nao mais 501 -- ver `busca_go/nucleo/relatorio.py`
`exportar_pdf`, fpdf2). DB isolado por teste (mesmo padrao de
`test_api_casos.py`)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import busca_go.nucleo.casos as casos_module
from busca_go.api import app
from busca_go.db import DB
from busca_go.nucleo import evidencia


@pytest.fixture
def client(tmp_path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    banco_teste = DB(db_path=tmp_path / "casos-teste.db")
    monkeypatch.setattr(casos_module, "default_db", lambda: banco_teste)
    # exportar_pdf agora grava relatorio.pdf de verdade em disco -- isola em
    # tmp_path pra nao poluir data/casos/ real com artefatos deste teste.
    monkeypatch.setattr(evidencia.settings, "DATA_DIR", tmp_path)
    with TestClient(app) as c:
        yield c


def test_relatorio_formato_pdf_200_com_content_type_correto(client: TestClient):
    r_caso = client.post(
        "/api/casos",
        json={"titulo": "Caso PDF", "tipo": "livre", "alvos": {}, "municipios": ["trindade"]},
    )
    caso_id = r_caso.json()["id"]

    r = client.get(f"/api/casos/{caso_id}/relatorio", params={"formato": "pdf"})

    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert f'filename="relatorio-{caso_id}.pdf"' in r.headers["content-disposition"]
    assert r.content.startswith(b"%PDF-")


def test_relatorio_formato_invalido_continua_400(client: TestClient):
    r_caso = client.post(
        "/api/casos",
        json={"titulo": "Caso X", "tipo": "livre", "alvos": {}, "municipios": ["trindade"]},
    )
    caso_id = r_caso.json()["id"]

    r = client.get(f"/api/casos/{caso_id}/relatorio", params={"formato": "docx"})

    assert r.status_code == 400
