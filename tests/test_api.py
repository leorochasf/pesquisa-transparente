"""Smoke tests da API e do CLI. Sem rede (somente endpoints que nao navegam)."""

import json
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from busca_go.api import app
from busca_go.db import DB
from busca_go.nucleo import casos as casos_module
from busca_go.nucleo import evidencia as evidencia_module


@pytest.fixture(autouse=True)
def _isolar_db_e_data_dir(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """DB e DATA_DIR isolados (mesmo motivo de `test_api_casos.py`): alguns
    testes deste arquivo entram no lifespan de verdade (`with TestClient(app)
    as c:`), que roda `recuperar_jobs_interrompidos` e
    `evidencia.backfill_evidencias` -- sem isolamento, tocaria o
    `data/casos.db`/`data/casos/` reais em vez de um banco de teste."""
    banco_teste = DB(db_path=tmp_path / "casos-teste.db")
    monkeypatch.setattr(casos_module, "default_db", lambda: banco_teste)
    monkeypatch.setattr(evidencia_module.settings, "DATA_DIR", tmp_path)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class _FakeClient:
    """Stub do NucleoClient para simular falhas sem rede."""

    def __init__(self, fetch=None):
        self._fetch = fetch

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def fetch_section(self, *a, **kw):
        if self._fetch:
            return await self._fetch(*a, **kw)
        return {"items": [], "cached": True, "source_url": ""}


# ---------- API ----------


def test_api_health(client: TestClient):
    r = client.get("/api/health")
    body = r.json()
    assert body["status"] in {"ok", "degraded"}
    assert "checks" in body
    assert "cache" in body["checks"]
    # playwright pode ou não estar instalado; só checa que a chave existe
    assert "playwright" in body["checks"]
    # cache deve estar sempre ok (testclient roda local)
    assert body["checks"]["cache"] is True


def test_api_config(client: TestClient):
    r = client.get("/api/config")
    assert r.status_code == 200
    data = r.json()
    assert "cache_days" in data
    assert "cache_db" in data
    assert data["headless"] is True


def test_api_config_expoe_secoes_catalogo(client: TestClient):
    """M2: /api/config expoe o catalogo canonico de secoes (estatico, de
    routes.SECOES) para o front usar como indicador sem disparar scraping."""
    from busca_go.nucleo.routes import SECOES

    r = client.get("/api/config")
    assert r.status_code == 200
    data = r.json()
    assert "secoes_catalogo" in data
    assert data["secoes_catalogo"] == SECOES
    # aditamentos voltou ao catalogo (per-municipio) -> 10 secoes.
    assert len(data["secoes_catalogo"]) == 10
    assert "aditamentos" in data["secoes_catalogo"]
    assert "licitacoes" in data["secoes_catalogo"]


def test_api_municipios_6(client: TestClient):
    r = client.get("/api/municipios")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 7
    slugs = {m["slug"] for m in data}
    assert slugs == {
        "rioverde",
        "senadorcanedo",
        "trindade",
        "cristalina",
        "itumbiara",
        "saomigueldoaraguaia",
        "caldazinha",
    }
    assert "goiania" not in slugs


def test_api_secoes_municipio_inexistente(client: TestClient):
    r = client.get("/api/secoes/inexistente")
    assert r.status_code == 404
    assert "nao cadastrado" in r.json()["detail"]


def test_api_secoes_estatico_reflete_tabela(client: TestClient):
    """/api/secoes/{slug} sai da tabela estatica (sem scraping): Senador Canedo
    expoe legislacao/licitacoes mas NAO `atas`."""
    r = client.get("/api/secoes/senadorcanedo")
    assert r.status_code == 200
    data = r.json()
    assert data["slug"] == "senadorcanedo"
    assert "atas" not in data["secoes"]
    assert "licitacoes" in data["secoes"]
    assert "legislacao" in data["secoes"]


def test_api_buscar_falha_scrape_vira_502_json_com_error_key(client: TestClient, monkeypatch):
    """Falha de scraping (ex.: 403 do portal) NUNCA vira 200 vazio: deve virar
    502 com corpo {"error": "<mensagem clara>"}."""

    async def boom(*a, **kw):
        raise RuntimeError("O portal do municipio recusou o acesso (HTTP 403).")

    monkeypatch.setattr("busca_go.api.NucleoClient", lambda *a, **kw: _FakeClient(fetch=boom))

    with TestClient(app) as c:
        r = c.get("/api/buscar/senadorcanedo/licitacoes")

    assert r.status_code == 502
    assert r.headers["content-type"].startswith("application/json")
    body = r.json()
    assert "error" in body
    assert "403" in body["error"]


def test_api_health_sem_lifespan_ativo_e_degraded_503(client: TestClient):
    """Fixture `client` nao entra no context manager -> lifespan nao roda ->
    sem browser compartilhado -> health deve reportar degraded com 503."""
    r = client.get("/api/health")
    body = r.json()
    assert body["checks"]["playwright"] is False
    assert body["status"] == "degraded"
    assert r.status_code == 503


def test_api_scraping_sem_browser_vira_503(client: TestClient, monkeypatch):
    """B1: sem Chromium disponivel (app.state.browser None), os endpoints de
    scraping respondem 503 com {"error": ...} pt-BR em vez de tentar navegar
    e quebrar. Fixa app.state.browser=None explicitamente (app e singleton de
    modulo, entao um teste anterior pode ter deixado um browser fechado la)."""
    monkeypatch.setattr(app.state, "browser", None, raising=False)

    rb = client.get("/api/buscar/rioverde/licitacoes?ano=2025")
    assert rb.status_code == 503
    assert "error" in rb.json()

    # /api/secoes agora e estatico (nao navega): responde 200 mesmo sem browser.
    rs = client.get("/api/secoes/rioverde")
    assert rs.status_code == 200
    assert "licitacoes" in rs.json()["secoes"]


def test_lifespan_sobe_degradado_quando_chromium_falha(monkeypatch):
    """B1: se chromium.launch() falhar no boot, o servidor SOBE mesmo assim
    (nao derruba o processo); /api/health responde 503 degraded com
    playwright:false e o scraping responde 503 com {"error": ...}."""

    class _FakeChromium:
        async def launch(self, **kw):
            raise RuntimeError("Executable doesn't exist (chromium nao instalado)")

    class _FakePW:
        chromium = _FakeChromium()

        async def stop(self):
            return None

    class _FakeStarter:
        async def start(self):
            return _FakePW()

    monkeypatch.setattr("busca_go.api.async_playwright", lambda: _FakeStarter())

    with TestClient(app) as c:  # entra no lifespan -> launch falha -> degradado
        h = c.get("/api/health")
        assert h.status_code == 503
        assert h.json()["checks"]["playwright"] is False

        rb = c.get("/api/buscar/rioverde/licitacoes?ano=2025")
        assert rb.status_code == 503
        assert "error" in rb.json()


def test_api_buscar_municipio_inexistente(client: TestClient):
    r = client.get("/api/buscar/inexistente/licitacoes")
    assert r.status_code == 404
    assert "nao cadastrado" in r.json()["detail"]


def test_api_buscar_secao_inexistente(client: TestClient):
    r = client.get("/api/buscar/rioverde/foobar")
    assert r.status_code == 404
    assert "desconhecida" in r.json()["detail"]


def test_api_buscar_secao_indisponivel_no_municipio(client: TestClient):
    """`atas` esta no catalogo mas Senador Canedo nao tem rota real -> 404."""
    with TestClient(app) as c:
        r = c.get("/api/buscar/senadorcanedo/atas")
    assert r.status_code == 404
    assert "atas" in r.json()["detail"]


def test_api_root_nao_serve_html(client: TestClient):
    """Back é só API agora — front vive em web-next. Raiz deve ser 404."""
    r = client.get("/")
    assert r.status_code == 404


def test_api_static_404(client: TestClient):
    """Mount /static foi removido; nenhum path /static deve responder."""
    r = client.get("/static/index.html")
    assert r.status_code == 404


# ---------- CLI (subprocess) ----------


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    cmd = [sys.executable, "-m", "busca_go.cli", *args]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=15)


def test_cli_municipios_6():
    proc = _run_cli("municipios")
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert len(data) == 7
    assert "cristalina" in {m["slug"] for m in data}
    assert "caldazinha" in {m["slug"] for m in data}


def test_cli_config():
    proc = _run_cli("config")
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert "cache_days" in data


def test_cli_cache_clear():
    proc = _run_cli("cache", "clear")
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert data["ok"] is True
    assert data["action"] == "clear"


def test_cli_buscar_municipio_inexistente_exit_2():
    proc = _run_cli("buscar", "foo", "licitacoes")
    assert proc.returncode == 2
    data = json.loads(proc.stdout)
    assert data["ok"] is False
    assert "nao cadastrado" in data["error"]


def test_cli_help_sai_codigo_zero():
    proc = _run_cli("--help")
    assert proc.returncode == 0
    assert "municipios" in proc.stdout
    assert "buscar" in proc.stdout
