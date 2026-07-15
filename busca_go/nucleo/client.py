"""Cliente Playwright para portais nucleogov (acessoainformacao.<m>.go.gov.br).

API:
    async with NucleoClient() as c:
        html = await c.navigate_and_render(url)
        result = await c.fetch_section(slug, 'licitacoes', ano=2025)

As secoes disponiveis por municipio vem da tabela estatica
`nucleo/routes.secoes_disponiveis(slug)` — nao ha mais descoberta de menu ao
vivo (o antigo `discover_sections` era heuristico e fragil; a tabela de rotas
reais o aposenta).

Cache automatico: cada fetch_section consulta o cache primeiro;
em miss, navega, parseia e grava. TTL via Settings.CACHE_DAYS.

DEPENDENCIA: binarios do Chromium (rode `playwright install chromium`
antes do primeiro uso). Sem isso, navigate_and_render levanta erro.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from ..cache import Cache, default_cache
from ..config import settings
from ..municipios import Municipio, get as get_mun
from . import capacidades, entidade
from .capacidades import Capacidade
from .parsers import ItemTransparencia, ParseError, parse_tabela_generica
from .routes import SecaoIndisponivel, resolve


_UA_CHROME = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


class NavigationError(RuntimeError):
    """Navegacao chegou a uma resposta HTTP de erro (portal recusou o acesso)."""


class NucleoClient:
    """Wrapper async sobre Playwright. 1 browser singleton."""

    def __init__(
        self,
        headless: bool | None = None,
        timeout_ms: int | None = None,
        cache_db: Path | None = None,
        browser: Browser | None = None,
    ) -> None:
        self.headless = headless if headless is not None else settings.HEADLESS
        self.timeout_ms = timeout_ms if timeout_ms is not None else settings.TIMEOUT_MS
        self._pw = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        # Browser compartilhado (ex.: lifespan da API) — se informado, este
        # client nao o fecha em close(); apenas fecha o context proprio.
        self._external_browser = browser
        self._cache = Cache(cache_db) if cache_db else default_cache()

    async def __aenter__(self) -> "NucleoClient":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def start(self) -> None:
        """Abre o browser (ou reaproveita um compartilhado) + context. Idempotente."""
        if self._context is not None:
            return
        if self._external_browser is not None:
            self._browser = self._external_browser
        else:
            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(headless=self.headless)
        # user_agent de Chrome desktop e obrigatorio: varios portais NucleoGov
        # (Rio Verde, Trindade) respondem 403 via WAF a qualquer requisicao com
        # UA contendo `HeadlessChrome` — inclusive na home. Com este UA custom,
        # todas as rotas confirmadas retornam 200 em modo headless.
        self._context = await self._browser.new_context(
            user_agent=_UA_CHROME,
            locale="pt-BR",
            extra_http_headers={"Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8"},
        )

    async def close(self) -> None:
        """Fecha o context proprio; fecha browser+playwright so se nao forem compartilhados. Idempotente."""
        if self._context is not None:
            try:
                await self._context.close()
            finally:
                self._context = None
        if self._external_browser is not None:
            self._browser = None
            return
        if self._browser is not None:
            try:
                await self._browser.close()
            finally:
                self._browser = None
        if self._pw is not None:
            try:
                await self._pw.stop()
            finally:
                self._pw = None

    # -------- navegacao --------

    async def _new_page(self) -> Page:
        if self._context is None:
            await self.start()
        assert self._context is not None
        page = await self._context.new_page()
        page.set_default_timeout(self.timeout_ms)
        return page

    async def navigate_and_render(self, url: str, wait_selector: str | None = None) -> str:
        """Navega ate `url`, espera render JS e devolve o HTML final.

        Args:
            url: URL completa (use routes.resolve para construir).
            wait_selector: seletor CSS opcional para garantir render
                           de elemento especifico antes de capturar.
        """
        page = await self._new_page()
        try:
            response = await page.goto(url, wait_until="networkidle", timeout=self.timeout_ms)
            if response is not None and not response.ok:
                raise NavigationError(
                    f"O portal do municipio recusou o acesso (HTTP {response.status})."
                )
            if wait_selector:
                try:
                    await page.wait_for_selector(wait_selector, timeout=self.timeout_ms)
                except Exception:
                    # Falhou em esperar seletor especifico: tenta domcontentloaded
                    await page.wait_for_load_state("domcontentloaded")
            else:
                # O nucleogov (SPA) as vezes preenche a tabela via XHR que
                # termina um pouco DEPOIS do evento networkidle. Espera
                # curta e best-effort por uma linha de dados; se a secao
                # for legitimamente vazia, o timeout apenas expira e segue.
                try:
                    await page.wait_for_selector("table td", timeout=5000)
                except Exception:
                    pass
            html = await page.content()
            return html
        finally:
            await page.close()

    # -------- fetch com cache --------

    async def fetch_section(
        self,
        slug: str,
        secao: str,
        **filtros: Any,
    ) -> dict[str, Any]:
        """Fluxo completo: resolve URL(s) -> checa cache -> navega -> parseia -> cacheia.

        Uma secao pode mapear para MAIS DE UMA pagina (ex.: `legislacao` =
        leis + decretos + portarias em Trindade). Neste caso, cada URL e
        buscada e os itens sao CONCATENADOS num unico resultado; cada item
        carrega sua propria `fonte` (URL de origem).

        Args:
            slug: identificador do municipio (ex.: 'senadorcanedo').
            secao: chave em SECOES (ex.: 'licitacoes').
            **filtros: parametros extras (ex.: ano=2025, cnpj='...').

        Returns:
            dict com chaves:
                items:      list[ItemTransparencia]
                source_url: URL(s) usada(s), separadas por ' | ' quando >1
                cached_at:  ISO timestamp OU None se cache miss recente
                cached:     bool (True = veio do cache)
                plataforma: plataforma do municipio
        """
        mun = get_mun(slug)
        urls = resolve(mun, secao, filtros)

        # 1. Tenta cache
        cached = self._cache.get(slug, secao, filtros)
        if cached is not None:
            cached["cached"] = True
            return cached

        # 2. CAL-F1 (AUDITORIA/rotas/revisao-caldazinha.md): secoes de sabor
        # "megasoft" (folha de Caldazinha) sao servidas por um controller SPA
        # (`servidores_mega`) que o scraper Playwright generico abaixo NAO
        # extrai -- devolveria sempre 0 itens (falso-vazio, o portal tem
        # registros reais). Desvia para a mesma via httpx que a busca por
        # entidade ja usa e valida ao vivo (`entidade._multi`), preservando o
        # scraper Playwright para as outras 6 cidades (nenhuma usa
        # modo_api="megasoft").
        cap = capacidades.resolver(slug, secao) if secao == "folha" else None
        if cap is not None and cap.modo_api == "megasoft":
            items_dict = await self._buscar_folha_megasoft(mun, cap, filtros)
            source_url = urls[0]
        else:
            # Navega e parseia cada sub-pagina, concatenando os itens.
            items_dict = []
            for url in urls:
                html = await self.navigate_and_render(url)
                try:
                    itens = parse_tabela_generica(html, secao=secao, fonte=url)
                except ParseError:
                    itens = []
                items_dict.extend(it.to_dict() for it in itens)
            source_url = " | ".join(urls)

        cached_at = time.time()
        payload: dict[str, Any] = {
            "items": items_dict,
            "source_url": source_url,
            "cached_at": cached_at,
            "cached": False,
            "plataforma": mun.plataforma,
        }

        # 3. Grava no cache
        self._cache.put(slug, secao, filtros, payload)
        return payload

    async def _buscar_folha_megasoft(
        self, mun: Municipio, cap: Capacidade, filtros: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Pagina a folha de sabor "megasoft" via httpx (sem Chromium).

        Mesma logica de paginacao/parsing de `entidade._multi`/`_grupo_folha`,
        so que sem filtro por nome (aqui e listagem de secao, nao busca por
        entidade) -- so `ano` (unico filtro que `/api/buscar` aceita hoje) e
        repassado, se presente.
        """
        params: dict[str, Any] = dict(cap.extra)
        ano = filtros.get("ano")
        if ano:
            params["ano"] = str(ano)
        itens: list[dict[str, Any]] = []
        offset = 0
        async with entidade._novo_client() as cli:
            while offset < entidade._MAX_ITENS_SERVER:
                pg = await entidade._multi(
                    cli, mun.url_base, cap.acao_listar, params, offset, entidade._PAGE, cap.modo_api
                )
                if not pg["dados"]:
                    break
                itens.extend(pg["dados"])
                offset += entidade._PAGE
                if pg["total"] and offset >= pg["total"]:
                    break
        fonte = resolve(mun, "folha")[0]
        return [
            ItemTransparencia(
                titulo=str(it.get("nome") or ""),
                data=str(it.get("mesAno") or ""),
                valor=str(it.get("totalLiquido") or ""),
                fonte=fonte,
                secao="folha",
                raw={k: str(v) for k, v in it.items() if k != "chave"},
            ).to_dict()
            for it in itens
        ]

    # -------- utilitarios estaticos --------

    @staticmethod
    def listar_municipios() -> list[dict[str, str]]:
        """Snapshot do registry para exibicao em CLI/UI."""
        from ..municipios import MUNICIPIOS

        return [
            {"slug": m.slug, "nome": m.nome, "plataforma": m.plataforma, "url_base": m.url_base}
            for m in MUNICIPIOS.values()
        ]


__all__ = ["NucleoClient", "SecaoIndisponivel", "NavigationError"]
