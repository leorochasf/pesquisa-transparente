"""API HTTP do busca-transparencia-goias.

Back-only: front vive em web-next (Next.js). Nenhum asset servidos daqui.

Endpoints:
    GET /api/municipios                    -> lista de municipios cadastrados
    GET /api/secoes/{slug}                 -> secoes disponiveis (tabela estatica)
    GET /api/buscar/{slug}/{secao}         -> busca itens (cache + nucleogov)
    GET /api/pesquisar/{slug}              -> busca por entidade (CPF/CNPJ/nome/termo)
    GET /api/anexos/{slug}/{secao}         -> lista anexos de um registro (lazy)
    GET /api/anexos/{slug}/{secao}/download-> baixa 1 anexo (PDF limpo)
    GET /api/config                        -> configuracao ativa
    GET /api/health                        -> health check

    -- caso/dossie (P2, aditivo -- ver AUDITORIA/refatoracao/04-blueprint.md §5) --
    POST /api/casos                        -> cria caso
    GET  /api/casos                        -> lista casos
    GET  /api/casos/{id}                   -> caso + itens + evidencias + anotacoes
    POST /api/casos/{id}/pesquisar         -> dispara busca assincrona -> {job_id}
    GET  /api/jobs/{job_id}                -> status/progresso do job
    POST /api/casos/{id}/itens             -> anexa item manualmente ao caso
    POST /api/casos/{id}/anotacoes         -> grava anotacao (do caso ou de 1 item)
    POST /api/casos/{id}/folha             -> fluxo manual de folha num passo -> {job_id}
                                               (ACEIT-F5/F6: persiste item + evidencia vinculada)

    -- relatorio/export do dossie (P5, ver AUDITORIA/refatoracao/04-blueprint.md §6.3) --
    GET  /api/casos/{id}/relatorio                  -> relatorio.md do caso (?formato=pdf indisponivel)
    GET  /api/casos/{id}/evidencias/{ev_id}/arquivo -> baixa o PDF/PNG de 1 evidencia do dossie

    -- agente investigador (P4, ver AUDITORIA/refatoracao/04-blueprint.md §6) --
    POST /api/casos/{id}/investigar        -> dispara o agente (OpenRouter) -> {job_id}
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Awaitable, Callable

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from playwright.async_api import async_playwright
from pydantic import BaseModel

from .agente import cabeca
from .config import settings
from .municipios import MUNICIPIOS
from .nucleo import anexos, casos, entidade, evidencia, relatorio
from .nucleo.client import NucleoClient
from .nucleo.routes import SECOES, SecaoIndisponivel, secoes_disponiveis
from .nucleo.sections import SECTIONS

logger = logging.getLogger(__name__)

# Mensagem pt-BR quando o Chromium nao esta disponivel (boot degradado, B1).
_NO_BROWSER_MSG = (
    "Servico de navegacao (Chromium) indisponivel no servidor. "
    "Rode 'playwright install chromium' e reinicie. Consultas que dependem "
    "de scraping estao temporariamente fora do ar."
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Sobe 1 Chromium compartilhado no boot; fecha no shutdown.

    Evita abrir/fechar 1 browser por requisicao (BUG-06). Cada requisicao
    ainda abre seu proprio BrowserContext (isolamento de cookies/sessao).

    B1: se o Chromium nao puder ser lancado (nao instalado, etc.), o
    servidor SOBE mesmo assim em modo degradado (browser=None): /api/health
    reporta 503 `playwright:false` e os endpoints de scraping respondem 503
    com `{"error": ...}` em vez de derrubar o processo no boot.
    """
    pw = None
    browser = None
    try:
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(headless=settings.HEADLESS)
    except Exception as exc:  # noqa: BLE001 — boot resiliente e intencional
        logger.warning(
            "Chromium indisponivel no boot (%s). Servidor subindo em modo "
            "degradado: scraping respondera 503 ate o Chromium ser instalado.",
            exc,
        )
        browser = None
    _app.state.playwright = pw
    _app.state.browser = browser
    # Jobs de busca (P2): referencias vivas das asyncio tasks (evita GC) +
    # recuperacao de jobs presos por um processo anterior que morreu no meio
    # (nunca fica 'rodando' fantasma — vira 'interrompida').
    _app.state.jobs_ativos = set()
    casos.recuperar_jobs_interrompidos()
    # Migracao idempotente (W2-F1): indexa na tabela `evidencias` o que ja
    # esta em manifesto.jsonl mas nunca foi indexado (evidencia coletada
    # antes desta correcao). Sem custo perceptivel em reboots normais --
    # INSERT OR IGNORE por id.
    evidencia.backfill_evidencias()
    try:
        yield
    finally:
        if browser is not None:
            await browser.close()
        if pw is not None:
            await pw.stop()


app = FastAPI(
    title="Busca Transparencia Goias",
    version="0.1.0",
    description="Hub de consulta de transparencia publica dos municipios goianos (portal nucleogov).",
    lifespan=lifespan,
)

# CORS — origens configuraveis via env BUSCA_GO_CORS_ORIGINS (csv, default "*").
# Necessario para front separado (ex.: Next.js em :3000) acessar este back.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# ---------- modelos ----------


class MunicipioOut(BaseModel):
    slug: str
    nome: str
    plataforma: str
    url_base: str


class SecaoInfo(BaseModel):
    slug: str
    descricao: str
    filtros: dict[str, str]


# ---------- helpers ----------


def _municipio(slug: str) -> MunicipioOut:
    if slug not in MUNICIPIOS:
        raise HTTPException(
            status_code=404,
            detail=f"Municipio '{slug}' nao cadastrado. Disponiveis: {sorted(MUNICIPIOS)}",
        )
    m = MUNICIPIOS[slug]
    return MunicipioOut(slug=m.slug, nome=m.nome, plataforma=m.plataforma, url_base=m.url_base)


# ---------- API ----------


@app.get("/api/health")
async def health() -> JSONResponse:
    checks: dict[str, bool] = {}

    # 1. Cache DB acessível
    try:
        from .cache import default_cache
        c = default_cache()
        c.get("__health__", "__health__")  # força criação se não existir
        with c._lock, c._connect() as conn:
            conn.execute("SELECT 1").fetchone()
        checks["cache"] = True
    except Exception:
        checks["cache"] = False

    # 2. Chromium do Playwright: usa o browser real do lifespan (nao
    # adivinha caminho de instalacao — consulta o estado ao vivo).
    browser = getattr(app.state, "browser", None)
    checks["playwright"] = browser is not None and browser.is_connected()

    ok = all(checks.values())
    status_code = 200 if ok else 503
    return JSONResponse(
        content={"status": "ok" if ok else "degraded", "checks": checks},
        status_code=status_code,
    )


@app.get("/api/config", response_model=dict[str, Any])
async def config() -> dict[str, Any]:
    return {
        "cache_db": str(settings.CACHE_DB),
        "cache_days": settings.CACHE_DAYS,
        "headless": settings.HEADLESS,
        "timeout_ms": settings.TIMEOUT_MS,
        # Catalogo canonico de secoes (estatico, de routes.SECOES). O front
        # usa o tamanho desta lista como indicador — sem disparar scraping.
        "secoes_catalogo": SECOES,
    }


@app.get("/api/municipios", response_model=list[MunicipioOut])
async def listar_municipios() -> list[MunicipioOut]:
    return [_municipio(s) for s in sorted(MUNICIPIOS)]


@app.get("/api/secoes/{slug}", response_model=dict[str, Any])
async def listar_secoes(slug: str) -> Any:
    """Secoes DISPONIVEIS do municipio, da tabela estatica de rotas reais.

    Nao ha mais scraping de menu ao vivo (o antigo `discover_sections` era
    heuristico e fragil — perdia ate secoes com dados, como `legislacao` em
    Rio Verde). A lista sai de `routes.secoes_disponiveis`, que reflete
    exatamente as rotas confirmadas ao vivo para aquele portal.
    """
    if slug not in MUNICIPIOS:
        raise HTTPException(
            404,
            f"Municipio '{slug}' nao cadastrado. Disponiveis: {sorted(MUNICIPIOS)}",
        )
    return {"slug": slug, "secoes": secoes_disponiveis(slug)}


@app.get("/api/buscar/{slug}/{secao}", response_model=dict[str, Any])
async def buscar(
    slug: str,
    secao: str,
    ano: int | None = None,
    cnpj: str | None = None,
    modalidade: str | None = None,
    numero: str | None = None,
    credor: str | None = None,
) -> Any:
    if slug not in MUNICIPIOS:
        raise HTTPException(
            404,
            f"Municipio '{slug}' nao cadastrado. Disponiveis: {sorted(MUNICIPIOS)}",
        )
    if secao not in SECOES:
        raise HTTPException(
            404,
            f"Secao '{secao}' desconhecida. Disponiveis: {SECOES}",
        )
    # A secao existe no catalogo, mas pode nao ter rota real neste municipio
    # (ex.: `atas` em Senador Canedo). Responde 404 direto, sem precisar de
    # browser — a checagem sai da mesma tabela estatica de /api/secoes.
    disponiveis = secoes_disponiveis(slug)
    if secao not in disponiveis:
        raise HTTPException(
            404,
            f"Secao '{secao}' nao disponivel em '{slug}'. Disponiveis: {disponiveis}",
        )
    filtros: dict[str, Any] = {
        k: v
        for k, v in {
            "ano": ano,
            "cnpj": cnpj,
            "modalidade": modalidade,
            "numero": numero,
            "credor": credor,
        }.items()
        if v is not None
    }
    # Validacao leve: se houver SECTIONS[secao], checa filtros
    if secao in SECTIONS:
        sec_cls = SECTIONS[secao]
        erros = sec_cls().validar_filtros(filtros)
        if erros:
            raise HTTPException(400, {"filtros_invalidos": erros})

    browser = getattr(app.state, "browser", None)
    if browser is None or not browser.is_connected():  # B1: boot degradado sem Chromium
        return JSONResponse(status_code=503, content={"error": _NO_BROWSER_MSG})
    async with NucleoClient(browser=browser) as c:
        try:
            result = await c.fetch_section(slug, secao, **filtros)
        except SecaoIndisponivel as exc:
            # Secao valida no catalogo, mas sem rota real neste municipio.
            raise HTTPException(404, str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except Exception as exc:
            # Falha de scraping/portal NUNCA vira 200 vazio (contrato de integracao):
            # o cache tambem nunca e populado nesse caminho (excecao ocorre antes
            # do NucleoClient.fetch_section chegar ao cache.put).
            return JSONResponse(
                status_code=502,
                content={"error": f"Falha ao buscar: {exc}"},
            )
    return result


@app.get("/api/pesquisar/{slug}", response_model=dict[str, Any])
async def pesquisar(
    slug: str,
    q: str,
    ano: int | None = None,
    mes: int | None = None,
) -> Any:
    """Busca por ENTIDADE: um campo unico (CPF/CNPJ/nome/termo) num municipio.

    Detecta o tipo da entrada e agrega contratos/licitacoes/dispensas (por
    documento ou termo) + folha (por nome+periodo), agrupando por secao. Usa
    httpx direto contra o `POST /api` do portal (JSON) — NAO depende do Chromium,
    portanto responde mesmo em boot degradado. Nao substitui `/api/buscar`
    (navegacao por secao continua no seu caminho Playwright).

    Falha de portal -> 502 {"error":...}; vazio legitimo -> grupos vazios.
    """
    if slug not in MUNICIPIOS:
        raise HTTPException(
            404,
            f"Municipio '{slug}' nao cadastrado. Disponiveis: {sorted(MUNICIPIOS)}",
        )
    if not q or not q.strip():
        raise HTTPException(400, "Parametro 'q' obrigatorio (CPF, CNPJ, nome ou termo).")
    try:
        return await entidade.pesquisar(slug, q, ano=ano, mes=mes)
    except entidade.PortalError as exc:
        return JSONResponse(status_code=502, content={"error": f"Falha ao pesquisar: {exc}"})


# ---------- anexos (download lazy de PDF) ----------

# Secoes documentais que expoem anexo (folha nao tem PDF de anexo).
_SECOES_ANEXO = {"contratos", "licitacoes", "dispensas"}


@app.get("/api/anexos/{slug}/{secao}", response_model=list[dict[str, str]])
async def listar_anexos(
    slug: str,
    secao: str,
    id: str,
    numero: str | None = None,
    ano: str | None = None,
) -> Any:
    """Lista os anexos de UM registro: `[{rotulo, ref}]` (ref = token opaco).

    Recebe os identificadores do registro (preservados em `ref_registro` pela
    busca por entidade). Nao carrega anexos de toda a busca — e sob demanda.
    Usa httpx direto (nao depende do Chromium).
    """
    if slug not in MUNICIPIOS:
        raise HTTPException(404, f"Municipio '{slug}' nao cadastrado. Disponiveis: {sorted(MUNICIPIOS)}")
    if secao not in _SECOES_ANEXO:
        raise HTTPException(404, f"Secao '{secao}' nao expoe anexos. Disponiveis: {sorted(_SECOES_ANEXO)}")
    registro = {"id": id, "numero": numero or "", "ano": ano or ""}
    try:
        return await anexos.listar_anexos(slug, secao, registro)
    except SecaoIndisponivel as exc:
        raise HTTPException(404, str(exc)) from exc
    except anexos.AnexoIndisponivel as exc:
        raise HTTPException(404, str(exc)) from exc
    except (anexos.AnexoError, entidade.PortalError) as exc:
        return JSONResponse(status_code=502, content={"error": f"Falha ao listar anexos: {exc}"})


@app.get("/api/anexos/{slug}/{secao}/download")
async def baixar_anexo(slug: str, secao: str, ref: str) -> Any:
    """Baixa UM anexo (por `ref` opaco) e responde o PDF limpo.

    `Content-Type: application/pdf` + `Content-Disposition: attachment`. Nunca
    expoe base64/JSON/URL interna do portal ao navegador. Falha -> 404/502 com
    `{"error":...}` em pt-BR (nunca stack trace).
    """
    if slug not in MUNICIPIOS:
        raise HTTPException(404, f"Municipio '{slug}' nao cadastrado. Disponiveis: {sorted(MUNICIPIOS)}")
    if secao not in _SECOES_ANEXO:
        raise HTTPException(404, f"Secao '{secao}' nao expoe anexos. Disponiveis: {sorted(_SECOES_ANEXO)}")
    try:
        blob, nome, content_type = await anexos.baixar_anexo(slug, secao, ref)
    except SecaoIndisponivel as exc:
        raise HTTPException(404, str(exc)) from exc
    except anexos.AnexoIndisponivel as exc:
        raise HTTPException(404, str(exc)) from exc
    except (anexos.AnexoError, entidade.PortalError) as exc:
        return JSONResponse(status_code=502, content={"error": f"Falha ao baixar anexo: {exc}"})
    return Response(
        content=blob,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


# ---------- caso/dossie (P2) ----------


class CasoIn(BaseModel):
    titulo: str
    tipo: str
    alvos: dict[str, Any] = {}
    municipios: list[str]


class ItemIn(BaseModel):
    municipio: str
    secao: str
    item: dict[str, Any]


class AnotacaoIn(BaseModel):
    item_id: str | None = None
    tag: str | None = None
    texto: str


class PesquisarCasoIn(BaseModel):
    q: str | None = None
    municipios: list[str] | None = None
    ano: int | None = None
    mes: int | None = None


class CompetenciaIn(BaseModel):
    ano: int
    mes: int


class FolhaCasoIn(BaseModel):
    municipio: str
    servidor: str
    matricula: str | None = None
    competencias: list[CompetenciaIn]


def _validar_municipios(slugs: list[str]) -> None:
    invalidos = [m for m in slugs if m not in MUNICIPIOS]
    if invalidos:
        raise HTTPException(
            404,
            f"Municipio(s) nao cadastrado(s): {invalidos}. Disponiveis: {sorted(MUNICIPIOS)}",
        )


def _obter_caso_ou_404(caso_id: str) -> dict[str, Any]:
    caso = casos.obter_caso(caso_id)
    if caso is None:
        raise HTTPException(404, f"Caso '{caso_id}' nao encontrado.")
    return caso


def _extrair_q(alvos: dict[str, Any]) -> str | None:
    return alvos.get("cnpj") or alvos.get("nome") or alvos.get("servidor")


# Ponto de encaixe do job de busca (blueprint P2 §7): por ora chama a busca
# por entidade EXISTENTE (`entidade.pesquisar`). Quando a busca Centi/combinada
# (P1) estiver pronta, trocar esta injecao (mesma assinatura: slug,q,ano,mes).
PESQUISAR_FN: Callable[..., Awaitable[dict[str, Any]]] = entidade.pesquisar


async def _executar_busca_caso(
    job_id: str,
    caso_id: str,
    q: str,
    municipios: list[str],
    ano: int | None,
    mes: int | None,
) -> None:
    total_itens = 0
    avisos: list[str] = []
    casos.marcar_busca_status(
        job_id,
        "rodando",
        progresso={"municipio_atual": None, "municipios_feitos": 0, "municipios_total": len(municipios)},
    )
    try:
        for i, slug in enumerate(municipios):
            casos.marcar_busca_status(
                job_id,
                "rodando",
                progresso={
                    "municipio_atual": slug,
                    "municipios_feitos": i,
                    "municipios_total": len(municipios),
                },
            )
            try:
                resultado = await PESQUISAR_FN(slug, q, ano=ano, mes=mes)
            except Exception as exc:  # noqa: BLE001 — 1 municipio falho nao derruba o job
                avisos.append(f"{slug}: falha na busca ({exc})")
                continue
            avisos.extend(resultado.get("avisos", []))
            for grupo in resultado.get("grupos", []):
                total_itens += casos.adicionar_itens_da_busca(
                    caso_id, slug, grupo["secao"], grupo.get("itens", [])
                )
        casos.marcar_busca_status(
            job_id,
            "concluida",
            progresso={
                "municipio_atual": None,
                "municipios_feitos": len(municipios),
                "municipios_total": len(municipios),
            },
            resultado_resumo={"total_itens": total_itens, "avisos": avisos},
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 — job nunca derruba o processo
        logger.exception("Job de busca %s (caso %s) falhou", job_id, caso_id)
        casos.marcar_busca_status(job_id, "erro", resultado_resumo={"erro": str(exc), "avisos": avisos})


@app.post("/api/casos", response_model=dict[str, Any])
async def criar_caso(body: CasoIn) -> Any:
    if not body.municipios:
        raise HTTPException(400, "Informe ao menos um municipio.")
    _validar_municipios(body.municipios)
    return casos.criar_caso(titulo=body.titulo, tipo=body.tipo, alvos=body.alvos, municipios=body.municipios)


@app.get("/api/casos", response_model=list[dict[str, Any]])
async def listar_casos() -> Any:
    return casos.listar_casos()


@app.get("/api/casos/{caso_id}", response_model=dict[str, Any])
async def obter_caso(caso_id: str) -> Any:
    return _obter_caso_ou_404(caso_id)


@app.post("/api/casos/{caso_id}/pesquisar", response_model=dict[str, str])
async def pesquisar_caso(caso_id: str, body: PesquisarCasoIn | None = None) -> Any:
    """Dispara a varredura do caso em background (asyncio task) e retorna
    `{job_id}` na hora. Estado do job vive na tabela `buscas` — sobrevive a
    refresh/poll; se o processo morrer no meio, o job fica `rodando` ate o
    proximo boot recuperar como `interrompida` (nunca fantasma)."""
    caso = _obter_caso_ou_404(caso_id)
    corpo = body or PesquisarCasoIn()
    q = corpo.q or _extrair_q(caso["alvos"])
    if not q:
        raise HTTPException(
            400,
            "Caso sem alvo pesquisavel: informe 'q' no corpo ou defina nome/cnpj/servidor nos alvos do caso.",
        )
    municipios = corpo.municipios or caso["municipios"]
    if not municipios:
        raise HTTPException(400, "Informe ao menos um municipio (corpo ou caso).")
    _validar_municipios(municipios)
    parametros = {"q": q, "municipios": municipios, "ano": corpo.ano, "mes": corpo.mes}
    job_id = casos.criar_busca(caso_id, parametros)
    task = asyncio.create_task(_executar_busca_caso(job_id, caso_id, q, municipios, corpo.ano, corpo.mes))
    app.state.jobs_ativos.add(task)
    task.add_done_callback(app.state.jobs_ativos.discard)
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}", response_model=dict[str, Any])
async def obter_job(job_id: str) -> Any:
    job = casos.obter_busca(job_id)
    if job is None:
        raise HTTPException(404, f"Job '{job_id}' nao encontrado.")
    return job


async def _executar_folha_caso(
    job_id: str,
    caso_id: str,
    slug: str,
    servidor: str,
    matricula: str | None,
    competencias: list[tuple[int, int]],
) -> None:
    """Job do fluxo manual de folha num passo so (ACEIT-F5): por competencia,
    persiste o item E captura a evidencia vinculada ao MESMO item (mesma
    infra job+polling de `/pesquisar`/`/investigar`). Homonimo sem matricula
    que desambigue encerra o job com erro claro listando candidatos
    (ACEIT-F5/F6 -- nunca escolhe por engano); falha de portal numa
    competencia isolada nao derruba as demais (mesmo padrao de
    `_executar_busca_caso`)."""
    total = len(competencias)
    casos.marcar_busca_status(
        job_id, "rodando", progresso={"competencia_atual": None, "feitas": 0, "total": total}
    )
    itens_ok: list[dict[str, Any]] = []
    falhas: list[dict[str, str]] = []
    avisos: list[str] = []
    try:
        for i, (ano, mes) in enumerate(competencias):
            casos.marcar_busca_status(
                job_id,
                "rodando",
                progresso={"competencia_atual": f"{mes:02d}/{ano}", "feitas": i, "total": total},
            )
            try:
                resultado = await evidencia.persistir_e_capturar_folha(
                    caso_id, slug, servidor, ano, mes, matricula=matricula
                )
            except evidencia.EvidenciaAmbigua as exc:
                casos.marcar_busca_status(
                    job_id,
                    "erro",
                    resultado_resumo={
                        "erro": str(exc),
                        "competencia": f"{mes:02d}/{ano}",
                        "itens": itens_ok,
                        "falhas": falhas,
                    },
                )
                return
            except evidencia.EvidenciaError as exc:
                falhas.append({"competencia": f"{mes:02d}/{ano}", "erro": str(exc)})
                continue
            itens_ok.append({"competencia": f"{mes:02d}/{ano}", "item_id": resultado["item_id"]})
            avisos.extend(resultado["avisos"])
        status = "concluida" if itens_ok else "erro"
        casos.marcar_busca_status(
            job_id,
            status,
            progresso={"competencia_atual": None, "feitas": total, "total": total},
            resultado_resumo={"itens": itens_ok, "falhas": falhas, "avisos": avisos},
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 — job nunca derruba o processo
        logger.exception("Job de folha %s (caso %s) falhou", job_id, caso_id)
        casos.marcar_busca_status(job_id, "erro", resultado_resumo={"erro": str(exc)})


@app.post("/api/casos/{caso_id}/folha", response_model=dict[str, str])
async def folha_caso(caso_id: str, body: FolhaCasoIn) -> Any:
    """Fluxo manual de folha num passo so (ACEIT-F5/F6, aceitacao final H2):
    por competencia, persiste o item no caso E captura a evidencia (PNG+JSON
    +manifesto) vinculada ao MESMO item -- quantificacao e prova juntas, sem
    2 chamadas separadas. Mesmo padrao job+polling de `/pesquisar`
    (`GET /api/jobs/{job_id}`)."""
    _obter_caso_ou_404(caso_id)
    _validar_municipios([body.municipio])
    if not body.servidor.strip():
        raise HTTPException(400, "Informe 'servidor' (nome ou matricula).")
    if not body.competencias:
        raise HTTPException(400, "Informe ao menos uma competencia ({ano, mes}).")
    for c in body.competencias:
        if not (1 <= c.mes <= 12):
            raise HTTPException(400, f"'mes' invalido: {c.mes} (competencia {c.ano}/{c.mes:02d}).")
    job_id = casos.criar_busca(
        caso_id,
        {
            "tipo": "folha",
            "municipio": body.municipio,
            "servidor": body.servidor,
            "matricula": body.matricula,
            "competencias": [{"ano": c.ano, "mes": c.mes} for c in body.competencias],
        },
    )
    competencias = [(c.ano, c.mes) for c in body.competencias]
    task = asyncio.create_task(
        _executar_folha_caso(job_id, caso_id, body.municipio, body.servidor, body.matricula, competencias)
    )
    app.state.jobs_ativos.add(task)
    task.add_done_callback(app.state.jobs_ativos.discard)
    return {"job_id": job_id}


@app.post("/api/casos/{caso_id}/itens", response_model=dict[str, str])
async def adicionar_item_caso(caso_id: str, body: ItemIn) -> Any:
    _obter_caso_ou_404(caso_id)
    _validar_municipios([body.municipio])
    item_id = casos.adicionar_item(caso_id, body.municipio, body.secao, body.item)
    return {"item_id": item_id}


@app.post("/api/casos/{caso_id}/anotacoes", response_model=dict[str, Any])
async def anotar_caso(caso_id: str, body: AnotacaoIn) -> Any:
    _obter_caso_ou_404(caso_id)
    if body.item_id is not None and casos.obter_item(body.item_id) is None:
        raise HTTPException(404, f"Item '{body.item_id}' nao encontrado.")
    return casos.adicionar_anotacao(caso_id, body.item_id, body.tag, body.texto)


# ---------- relatorio/export do dossie (P5) ----------


@app.get("/api/casos/{caso_id}/relatorio")
async def relatorio_caso(caso_id: str, formato: str = "md") -> Any:
    """Relatorio do dossie (blueprint §6.3): sintese, achados por procedimento
    com links relativos aos PDFs/PNGs do dossie, quantificacao (folha),
    lacunas e indice de evidencias com sha256. `formato=md` (default) devolve
    o markdown e grava `relatorio.md` em disco (regeneravel). `formato=pdf`
    devolve o arquivo PDF gerado (`fpdf2`), gravado como `relatorio.pdf`."""
    _obter_caso_ou_404(caso_id)
    if formato == "pdf":
        try:
            caminho_pdf = relatorio.exportar_pdf(caso_id)
        except relatorio.RelatorioPdfIndisponivel as exc:
            raise HTTPException(501, str(exc)) from exc
        return Response(
            content=caminho_pdf.read_bytes(),
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="relatorio-{caso_id}.pdf"'},
        )
    if formato != "md":
        raise HTTPException(400, f"Formato '{formato}' desconhecido. Use 'md' ou 'pdf'.")
    caminho = relatorio.salvar_relatorio(caso_id)
    return Response(content=caminho.read_text(encoding="utf-8"), media_type="text/markdown; charset=utf-8")


@app.get("/api/casos/{caso_id}/evidencias/{evidencia_id}/arquivo")
async def arquivo_evidencia(caso_id: str, evidencia_id: str) -> Any:
    """Serve o PDF/PNG de UMA evidencia do manifesto (streaming de arquivo
    local). Nunca serve fora de `data/casos/<id>/` -- caminho sempre validado
    (`relatorio.resolver_arquivo_evidencia`)."""
    _obter_caso_ou_404(caso_id)
    try:
        resultado = relatorio.resolver_arquivo_evidencia(caso_id, evidencia_id)
    except relatorio.CaminhoEvidenciaInvalido as exc:
        raise HTTPException(400, str(exc)) from exc
    if resultado is None:
        raise HTTPException(404, f"Evidencia '{evidencia_id}' nao encontrada no caso '{caso_id}'.")
    caminho, content_type, nome = resultado
    return Response(
        content=caminho.read_bytes(),
        media_type=content_type,
        headers={"Content-Disposition": f'inline; filename="{nome}"'},
    )


# ---------- agente investigador (P4) ----------


class InvestigarCasoIn(BaseModel):
    descricao: str | None = None


def _descricao_padrao_caso(caso: dict[str, Any]) -> str:
    alvos = ", ".join(f"{k}={v}" for k, v in (caso.get("alvos") or {}).items() if v)
    return f"{caso['titulo']} ({caso['tipo']}) -- municipios: {', '.join(caso['municipios'])}; alvos: {alvos or '-'}."


async def _executar_investigacao_caso(job_id: str, caso_id: str, descricao: str) -> None:
    """Roda o agente cabeca/worker em background (mesma infra de job+polling
    do P2, tabela `buscas` -- blueprint §5: 'o mesmo padrao serve
    /api/casos/{id}/investigar')."""
    casos.marcar_busca_status(job_id, "rodando", progresso={"etapa": "planejando"})
    try:
        resultado = await cabeca.investigar(
            caso_id,
            descricao,
            api_key=settings.OPENROUTER_API_KEY or "",
            base_url=settings.OPENROUTER_BASE_URL,
            modelo_cabeca=settings.OPENROUTER_MODEL_CABECA,
            modelo_worker=settings.OPENROUTER_MODEL_WORKER,
            max_subtarefas=settings.AGENTE_MAX_SUBTAREFAS,
            max_iter_worker=settings.AGENTE_MAX_ITER_WORKER,
            teto_tokens=settings.AGENTE_TETO_TOKENS,
            teto_tempo_s=settings.AGENTE_TETO_TEMPO_S,
        )
        # Review R4 F3: planejamento falhou por completo (ex.: model-id invalido,
        # OpenRouter fora do ar) -- nao ha subtarefa executada nem plano; o job
        # nao pode terminar como "concluida" (enganaria quem so olha o status).
        falhou_totalmente = not resultado.subtarefas_executadas and any(
            lac.subtarefa_id == "planejamento" for lac in resultado.lacunas
        )
        casos.marcar_busca_status(
            job_id,
            "erro" if falhou_totalmente else "concluida",
            progresso={
                "etapa": "erro" if falhou_totalmente else "concluida",
                "subtarefas_ok": len(resultado.subtarefas_executadas),
                "lacunas": len(resultado.lacunas),
            },
            resultado_resumo={
                "erro": resultado.lacunas[0].motivo if falhou_totalmente else None,
                "relatorio_path": resultado.relatorio_path,
                "subtarefas_ok": len(resultado.subtarefas_executadas),
                "lacunas": [lac.descricao for lac in resultado.lacunas],
                "tokens_total": resultado.custo.tokens_total,
                "custo_usd": resultado.custo.custo_usd,
                "teto_atingido": resultado.teto_atingido,
            },
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 — job nunca derruba o processo
        logger.exception("Job de investigacao %s (caso %s) falhou", job_id, caso_id)
        casos.marcar_busca_status(job_id, "erro", resultado_resumo={"erro": str(exc)})


@app.post("/api/casos/{caso_id}/investigar", response_model=dict[str, str])
async def investigar_caso(caso_id: str, body: InvestigarCasoIn | None = None) -> Any:
    """Dispara o agente investigador (cabeca/worker via OpenRouter, blueprint
    §6) em background e retorna `{job_id}` na hora -- mesmo padrao
    job+polling de `/pesquisar` (`GET /api/jobs/{job_id}`)."""
    caso = _obter_caso_ou_404(caso_id)
    if not settings.OPENROUTER_API_KEY:
        raise HTTPException(400, "OPENROUTER_API_KEY nao configurada (.env) -- agente investigador indisponivel.")
    corpo = body or InvestigarCasoIn()
    descricao = corpo.descricao or _descricao_padrao_caso(caso)
    job_id = casos.criar_busca(caso_id, {"tipo": "investigacao", "descricao": descricao})
    task = asyncio.create_task(_executar_investigacao_caso(job_id, caso_id, descricao))
    app.state.jobs_ativos.add(task)
    task.add_done_callback(app.state.jobs_ativos.discard)
    return {"job_id": job_id}


__all__ = ["app"]
