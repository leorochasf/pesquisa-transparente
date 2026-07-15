"""Testes smoke para busca_go.nucleo.client (sem rede)."""

import asyncio
import gc
import json
from urllib.parse import parse_qs

import httpx
import pytest

from busca_go.cache import Cache
from busca_go.nucleo import entidade
from busca_go.nucleo.client import NavigationError, NucleoClient


@pytest.fixture
def cache_path(tmp_path):
    """Fixture: cria path, usa gc.collect() no teardown pra liberar
    handles sqlite3 no Windows antes do tmp_path ser removido."""
    p = tmp_path / "t.db"
    yield p
    gc.collect()


def test_listar_municipios_tem_6():
    snap = NucleoClient.listar_municipios()
    assert len(snap) == 7
    assert all("url_base" in m and "slug" in m for m in snap)
    assert {m["slug"] for m in snap} == {
        "rioverde",
        "senadorcanedo",
        "trindade",
        "cristalina",
        "itumbiara",
        "saomigueldoaraguaia",
        "caldazinha",
    }


def test_constroi_client_sem_erro(cache_path):
    """Navegador ainda nao foi aberto: deve ser lazy."""
    c = NucleoClient(cache_db=cache_path, headless=True)
    assert c._browser is None


def test_cache_hit_sem_navegacao(cache_path):
    """Pre-popula o cache; fetch_section deve retornar sem chamar browser."""
    c = NucleoClient(cache_db=cache_path, headless=True)
    cache = Cache(db_path=cache_path)
    cache.put(
        "rioverde",
        "licitacoes",
        {"ano": 2025},
        {
            "items": [{"titulo": "fake", "data": "01/01/2025"}],
            "source_url": "https://acessoainformacao.rioverde.go.gov.br/cidadao/informacao/licitacoes?ano=2025",
            "cached_at": 1700000000.0,
            "cached": False,
            "plataforma": "nucleogov",
        },
    )
    result = asyncio.run(c.fetch_section("rioverde", "licitacoes", ano=2025))
    assert result["cached"] is True
    assert result["items"][0]["titulo"] == "fake"
    assert c._browser is None


def test_navigation_error_propaga_e_nao_cacheia(cache_path):
    """Falha de navegacao (ex.: HTTP 403 do portal) deve propagar como
    excecao e NUNCA gravar payload no cache (BUG-02 + BUG-05)."""
    c = NucleoClient(cache_db=cache_path, headless=True)

    async def fake_navigate(url, wait_selector=None):
        raise NavigationError("O portal do municipio recusou o acesso (HTTP 403).")

    c.navigate_and_render = fake_navigate  # type: ignore[method-assign]

    with pytest.raises(NavigationError):
        asyncio.run(c.fetch_section("rioverde", "licitacoes", ano=2025))

    cache = Cache(db_path=cache_path)
    assert cache.get("rioverde", "licitacoes", {"ano": 2025}) is None


def test_legislacao_multi_rota_concatena(cache_path):
    """Uma secao com varias sub-paginas (legislacao em Trindade = 3 URLs) tem
    os itens de TODAS as paginas concatenados num unico resultado, cada item
    carregando sua propria `fonte`. Usa stub de navigate_and_render (sem rede),
    devolvendo uma tabela distinta por URL."""
    c = NucleoClient(cache_db=cache_path, headless=True)

    tabelas = {
        "leis": "<table><tr><th>Numero</th><th>Ementa</th></tr><tr><td>Lei 1</td><td>ementa a</td></tr></table>",
        "decretos": "<table><tr><th>Numero</th><th>Ementa</th></tr><tr><td>Decreto 2</td><td>ementa b</td></tr></table>",
        "portarias": "<table><tr><th>Numero</th><th>Ementa</th></tr><tr><td>Portaria 3</td><td>ementa c</td></tr></table>",
    }

    async def fake_navigate(url, wait_selector=None):
        for tipo, html in tabelas.items():
            if url.endswith(tipo):
                return html
        raise AssertionError(f"URL inesperada: {url}")

    c.navigate_and_render = fake_navigate  # type: ignore[method-assign]

    result = asyncio.run(c.fetch_section("trindade", "legislacao"))
    titulos = [it["titulo"] for it in result["items"]]
    assert titulos == ["Lei 1", "Decreto 2", "Portaria 3"]
    # cada item aponta para a sub-pagina de origem
    fontes = {it["fonte"].rsplit("/", 1)[-1] for it in result["items"]}
    assert fontes == {"leis", "decretos", "portarias"}
    # source_url do payload lista as 3 sub-paginas
    assert result["source_url"].count(" | ") == 2


def test_secao_indisponivel_sem_navegar(cache_path):
    """Municipio sem rota para a secao: erro vem de routes, nao do browser."""
    from busca_go.nucleo.routes import SecaoIndisponivel

    c = NucleoClient(cache_db=cache_path, headless=True)
    # Senador Canedo nao expoe `atas`.
    with pytest.raises(SecaoIndisponivel):
        asyncio.run(c.fetch_section("senadorcanedo", "atas"))
    assert c._browser is None


# --------------------------------------------------------------------------- #
# CAL-F1 (AUDITORIA/rotas/revisao-caldazinha.md): folha "megasoft" via httpx
# --------------------------------------------------------------------------- #


def test_folha_caldazinha_megasoft_via_httpx_nao_scraper(cache_path, monkeypatch):
    """A busca antiga (`/api/buscar` -> `fetch_section`) NAO pode devolver a
    folha de Caldazinha vazia: o scraper Playwright generico nao extrai a
    tabela do controller `servidores_mega` (falso-vazio real, achado da
    revisao). O fix desvia para a mesma via httpx da busca por entidade."""
    c = NucleoClient(cache_db=cache_path, headless=True)

    async def fake_navigate(url, wait_selector=None):
        raise AssertionError(f"nao deveria navegar via Playwright para folha megasoft: {url}")

    c.navigate_and_render = fake_navigate  # type: ignore[method-assign]

    rows = [
        {"matricula": 901, "nome": "ADAO TESTE DE EXEMPLO", "mesAno": "06/2026",
         "totalLiquido": 2555.93, "cpf": "xxx.795.191-xx"},
        {"matricula": 902, "nome": "ADRIANA TESTE DE EXEMPLO", "mesAno": "06/2026",
         "totalLiquido": 2658.67, "cpf": "xxx.467.741-xx"},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        form = parse_qs(request.content.decode())
        blk = json.loads(form["params"][0])["k1"]
        assert blk["acao"] == "megasoft/servidores"
        assert blk["codigosDoOrgao"] == "22,23,24,25,26"
        assert "limit" not in blk  # paginacao por pagina/tamanhoDaPagina, nao offset
        return httpx.Response(200, json={"k1": {"total": len(rows), "registros": rows}})

    monkeypatch.setattr(
        entidade, "_novo_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )

    result = asyncio.run(c.fetch_section("caldazinha", "folha"))
    assert len(result["items"]) == 2
    assert result["items"][0]["titulo"] == "ADAO TESTE DE EXEMPLO"
    assert result["items"][0]["valor"] == "2555.93"
    assert result["items"][0]["raw"]["cpf"] == "xxx.795.191-xx"
    assert result["cached"] is False

    # cache gravado com os itens reais (proxima chamada nao re-navega/re-posta)
    cache = Cache(db_path=cache_path)
    cacheado = cache.get("caldazinha", "folha", {})
    assert cacheado is not None
    assert len(cacheado["items"]) == 2


def test_folha_trindade_continua_via_scraper_playwright(cache_path):
    """Isolamento: folha de Trindade (`modo_api='padrao'`) continua no
    caminho Playwright de sempre -- nao desvia para httpx."""
    c = NucleoClient(cache_db=cache_path, headless=True)
    html = (
        "<table><tr><th>Nome</th><th>Cargo</th></tr>"
        "<tr><td>FULANO DA SILVA</td><td>MOTORISTA</td></tr></table>"
    )
    chamadas = {"n": 0}

    async def fake_navigate(url, wait_selector=None):
        chamadas["n"] += 1
        return html

    c.navigate_and_render = fake_navigate  # type: ignore[method-assign]

    result = asyncio.run(c.fetch_section("trindade", "folha"))
    assert chamadas["n"] == 1
    assert result["items"][0]["titulo"] == "FULANO DA SILVA"
