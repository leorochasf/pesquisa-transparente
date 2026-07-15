"""Testes do download lazy de anexos (modo A base64 / modo B url assinada).

Sem rede: o POST /api multi_request e os GET de arquivo sao stubados com
httpx.MockTransport, reproduzindo os formatos reais observados ao vivo:
- Modo A (Senador Canedo): listarAnexos -> {k1:{total,dados}}; downloadAnexo ->
  {k1:{anexo:"<base64>"}}.
- Modo B (Trindade): busca_avancada traz `anexos:[{id,titulo,download_url}]`; a
  download_url e um GET direto que devolve o PDF binario.
"""

from __future__ import annotations

import base64
import json
from urllib.parse import parse_qs

import httpx
import pytest

from busca_go.nucleo import anexos

# PDF de teste (magic bytes reais para o content-type ser detectado como pdf).
_PDF = b"%PDF-1.7\n%fake pdf body\n%%EOF\n"
_PDF_B64 = base64.b64encode(_PDF).decode("ascii")

# Anexos modo A (Senador Canedo), formato do listarAnexos real.
_SC_ANEXOS = [
    {"chave": "26000000000019324", "numero_contrato": "0343/26", "nome": "CONTRATO - PNCP",
     "descricao": "CONTRATO - PNCP", "tipo_arquivo": "pdf",
     "url": "http://45.65.223.37:8082/api/transparencia/contratos/anexos/arquivo?id=1",
     "id": "26000000000019324"},
    {"chave": "26000000000019325", "nome": "EXTRATO CONTRATO - PNCP",
     "tipo_arquivo": "pdf", "id": "26000000000019325"},
]

# Registro modo B (Trindade), formato do busca_avancada real (anexos embutidos).
_TRINDADE_CONTRATO = {
    "id": "1554", "contrato_id": "1554", "numero": "067", "ano": "2026",
    "anexos": [
        {"id": "40376", "titulo": "24. Extrato do Contrato - DOM 30 06 2026.pdf",
         "download_url": "https://nucleogov.s3.us-east-2.amazonaws.com/pf_trindade/a.pdf?sig=1"},
        {"id": "40377", "titulo": "23. Contrato 067.2026 - DF HALLEX.pdf",
         "download_url": "https://nucleogov.s3.us-east-2.amazonaws.com/pf_trindade/b.pdf?sig=2"},
    ],
}


def make_portal(*, sc_anexos=None, download_ok=True, trindade=None, busca_vazia=False):
    """MockTransport que responde POST /api (modo A e B) e GET de arquivo (modo B)."""
    sc = _SC_ANEXOS if sc_anexos is None else sc_anexos
    trin = _TRINDADE_CONTRATO if trindade is None else trindade

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            url = str(request.url)
            # Armadilha Senador Canedo: o `url` do anexo (IP 45.65...) da 401.
            if "45.65" in url:
                return httpx.Response(401, json={"status": "error", "message": "Token not found."})
            # URL assinada S3 (modo B) ou link publico Centi (modo C) -> PDF.
            return httpx.Response(200, content=_PDF, headers={"content-type": "application/pdf"})

        assert request.url.path == "/api"
        form = parse_qs(request.content.decode())
        blk = json.loads(form["params"][0])["k1"]
        acao = blk["acao"]

        if acao == "contratos_frl/listarAnexos":
            return httpx.Response(200, json={"k1": {"total": len(sc), "dados": sc}})
        if acao == "contratos_frl/listarAditivos":
            return httpx.Response(200, json={"k1": {"total": 0, "dados": []}})
        if acao == "contratos_frl/downloadAnexo":
            if not download_ok:
                return httpx.Response(200, json={"k1": {"erro": "sem arquivo"}})
            return httpx.Response(200, json={"k1": {"anexo": _PDF_B64}})
        if acao == "contratos/busca_avancada":
            termo = blk.get("busca") or ""
            rows = [] if busca_vazia else ([trin] if termo in (trin["numero"], trin["id"]) else [])
            off, cnt = (int(x) for x in blk["limit"].split(","))
            return httpx.Response(200, json={"k1": {"total": len(rows), "dados": rows[off:off + cnt]}})
        return httpx.Response(200, json=[])

    return httpx.MockTransport(handler)


def _client(transport):
    return httpx.AsyncClient(transport=transport, base_url="https://x")


# --------------------------------------------------------------------------- #
# Modo A — Senador Canedo (base64)
# --------------------------------------------------------------------------- #


async def test_modo_a_lista_anexos():
    """SC contratos: listar devolve [{rotulo, ref}] com o rotulo humano do anexo."""
    async with _client(make_portal()) as cli:
        lst = await anexos.listar_anexos(
            "senadorcanedo", "contratos", {"id": "26000000000001074", "numero": "0343/26", "ano": "2026"}, client=cli,
        )
    assert [a["rotulo"] for a in lst] == ["CONTRATO - PNCP", "EXTRATO CONTRATO - PNCP"]
    assert all(a["ref"] for a in lst)


async def test_modo_a_baixa_decodifica_base64_e_nomeia_pdf():
    """Download modo A: decodifica o base64 e nomeia o arquivo .pdf."""
    async with _client(make_portal()) as cli:
        lst = await anexos.listar_anexos(
            "senadorcanedo", "contratos", {"id": "1", "numero": "0343/26", "ano": "2026"}, client=cli,
        )
        blob, nome, ctype = await anexos.baixar_anexo("senadorcanedo", "contratos", lst[0]["ref"], client=cli)
    assert blob == _PDF
    assert blob[:5] == b"%PDF-"
    assert ctype == "application/pdf"
    assert nome == "CONTRATO - PNCP.pdf"


async def test_modo_a_download_sem_arquivo_vira_indisponivel():
    """downloadAnexo sem base64 -> AnexoIndisponivel (404), nunca 200 corrompido."""
    async with _client(make_portal(download_ok=False)) as cli:
        lst = await anexos.listar_anexos("senadorcanedo", "contratos", {"id": "1", "ano": "2026"}, client=cli)
        with pytest.raises(anexos.AnexoIndisponivel):
            await anexos.baixar_anexo("senadorcanedo", "contratos", lst[0]["ref"], client=cli)


async def test_modo_a_registro_sem_anexo_lista_vazia():
    """Registro sem anexo (listarAnexos total:0) -> lista vazia, nao quebra."""
    async with _client(make_portal(sc_anexos=[])) as cli:
        lst = await anexos.listar_anexos("senadorcanedo", "contratos", {"id": "1", "ano": "2026"}, client=cli)
    assert lst == []


async def test_modo_a_portal_erro_propaga_portalerror():
    """listarAnexos com HTTP != 200 -> PortalError (endpoint traduz para 502)."""

    def handler(request):
        return httpx.Response(503, text="down")

    from busca_go.nucleo import entidade
    async with _client(httpx.MockTransport(handler)) as cli:
        with pytest.raises(entidade.PortalError):
            await anexos.listar_anexos("senadorcanedo", "contratos", {"id": "1", "ano": "2026"}, client=cli)


# --------------------------------------------------------------------------- #
# Modo C — Centi (cristalina/itumbiara/saomiguel): url publica direta no anexo
# --------------------------------------------------------------------------- #


async def test_modo_c_url_direta_quando_downloadanexo_nao_existe():
    """Centi: downloadAnexo responde 'Acao nao encontrada'; o `url` do anexo baixa o PDF."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            assert "centi" in str(request.url)
            return httpx.Response(200, content=_PDF)  # Centi nao manda content-type
        blk = json.loads(parse_qs(request.content.decode())["params"][0])["k1"]
        assert blk["acao"].endswith("/downloadAnexo")
        return httpx.Response(200, json={"k1": "Acao nao encontrada"})

    ref = anexos._encode_ref({
        "m": "A", "acao": "contratos_cnt/downloadAnexo",
        "item": {"nome": "empenho_79884.pdf", "descricao": "Contrato Original",
                 "url": "https://api.centi.com.br/portal/v2/documento/go/cristalina/download/kOV9"},
    })
    async with _client(httpx.MockTransport(handler)) as cli:
        blob, nome, ctype = await anexos.baixar_anexo("cristalina", "contratos", ref, client=cli)
    assert blob == _PDF
    assert blob[:5] == b"%PDF-"
    assert nome == "empenho_79884.pdf"
    assert ctype == "application/pdf"  # detectado pelos magic bytes


# --------------------------------------------------------------------------- #
# Modo B — Trindade (url assinada, reobter fresco)
# --------------------------------------------------------------------------- #


async def test_modo_b_lista_anexos_embutidos():
    """Trindade: listar reobtem o registro fresco e le o array `anexos`."""
    async with _client(make_portal()) as cli:
        lst = await anexos.listar_anexos(
            "trindade", "contratos", {"id": "1554", "numero": "067", "ano": "2026"}, client=cli,
        )
    assert len(lst) == 2
    assert lst[0]["rotulo"].startswith("24. Extrato do Contrato")


async def test_modo_b_baixa_repassa_binario():
    """Download modo B: reobtem fresco, GET na URL assinada, repassa o PDF binario."""
    async with _client(make_portal()) as cli:
        lst = await anexos.listar_anexos("trindade", "contratos", {"id": "1554", "numero": "067"}, client=cli)
        blob, nome, ctype = await anexos.baixar_anexo("trindade", "contratos", lst[0]["ref"], client=cli)
    assert blob == _PDF
    assert ctype == "application/pdf"
    assert nome.endswith(".pdf")


async def test_modo_b_fallback_para_url_quando_refetch_nao_acha():
    """Se o reobter fresco nao reencontrar o registro, usa a URL do proprio ref."""
    # ref manual: rid que nao casa (busca vazia), mas com url embutida valida.
    ref = anexos._encode_ref({
        "m": "B", "s": "contratos", "rid": "999", "numero": "999", "aid": "40376",
        "url": "https://nucleogov.s3.us-east-2.amazonaws.com/pf_trindade/a.pdf?sig=1",
        "nome": "Extrato.pdf",
    })
    async with _client(make_portal(busca_vazia=True)) as cli:
        blob, nome, ctype = await anexos.baixar_anexo("trindade", "contratos", ref, client=cli)
    assert blob == _PDF
    assert nome == "Extrato.pdf"


async def test_modo_b_registro_nao_encontrado_lista_vazia():
    """Trindade: registro nao reencontrado no reobter -> lista vazia."""
    async with _client(make_portal(busca_vazia=True)) as cli:
        lst = await anexos.listar_anexos("trindade", "contratos", {"id": "1554", "numero": "067"}, client=cli)
    assert lst == []


# --------------------------------------------------------------------------- #
# Token / erros
# --------------------------------------------------------------------------- #


async def test_ref_invalida_vira_indisponivel():
    """ref opaca corrompida -> AnexoIndisponivel (404), nunca stack trace."""
    async with _client(make_portal()) as cli:
        with pytest.raises(anexos.AnexoIndisponivel):
            await anexos.baixar_anexo("trindade", "contratos", "nao-e-base64-valido!!", client=cli)


async def test_ref_com_assinatura_adulterada_e_rejeitada():
    """ref com JSON valido mas assinatura HMAC trocada -> AnexoIndisponivel, sem GET."""
    ref_valido = anexos._encode_ref({
        "m": "A", "acao": "contratos_frl/downloadAnexo",
        "item": {"nome": "x.pdf", "url": "https://api.centi.com.br/x"},
    })
    envelope, _, _assinatura = ref_valido.rpartition(".")
    ref_adulterado = f"{envelope}.0000000000000000000000000000000000000000000000000000000000000000"

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("nao deveria chegar a fazer nenhuma chamada de rede")

    async with _client(httpx.MockTransport(handler)) as cli:
        with pytest.raises(anexos.AnexoIndisponivel):
            await anexos.baixar_anexo("cristalina", "contratos", ref_adulterado, client=cli)


async def test_ssrf_modo_a_host_fora_da_allowlist_e_recusado():
    """SSRF: ref forjado com `url` apontando para metadata de cloud -> recusado, sem GET."""
    ref = anexos._encode_ref({
        "m": "A", "acao": "contratos_frl/downloadAnexo",
        "item": {"nome": "x.pdf", "url": "http://169.254.169.254/latest/meta-data/"},
    })

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            raise AssertionError(f"GET nao deveria ter sido feito para {request.url}")
        # downloadAnexo sem base64 -> cai no fallback _tentar_url_direta.
        return httpx.Response(200, json={"k1": {"erro": "sem arquivo"}})

    async with _client(httpx.MockTransport(handler)) as cli:
        with pytest.raises(anexos.AnexoIndisponivel):
            await anexos.baixar_anexo("cristalina", "contratos", ref, client=cli)


async def test_ssrf_modo_a_host_desconhecido_e_recusado():
    """SSRF: ref forjado com `url` para host arbitrario (nao allowlisted) -> recusado."""
    ref = anexos._encode_ref({
        "m": "A", "acao": "contratos_frl/downloadAnexo",
        "item": {"nome": "x.pdf", "url": "http://example.com/evil.pdf"},
    })

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            raise AssertionError(f"GET nao deveria ter sido feito para {request.url}")
        return httpx.Response(200, json={"k1": {"erro": "sem arquivo"}})

    async with _client(httpx.MockTransport(handler)) as cli:
        with pytest.raises(anexos.AnexoIndisponivel):
            await anexos.baixar_anexo("cristalina", "contratos", ref, client=cli)


async def test_ssrf_modo_b_fallback_url_fora_da_allowlist_e_recusado():
    """SSRF: `ref` modo B forjado com `url` fora da allowlist -> recusado, sem GET."""
    ref = anexos._encode_ref({
        "m": "B", "s": "contratos", "rid": "999", "numero": "999", "aid": "40376",
        "url": "http://10.0.0.5:8000/admin",
        "nome": "Extrato.pdf",
    })

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            raise AssertionError(f"GET nao deveria ter sido feito para {request.url}")
        return httpx.Response(200, json={"k1": {"total": 0, "dados": []}})

    async with _client(httpx.MockTransport(handler)) as cli:
        with pytest.raises(anexos.AnexoIndisponivel):
            await anexos.baixar_anexo("trindade", "contratos", ref, client=cli)


def test_nome_arquivo_saneia_e_garante_extensao():
    assert anexos._nome_arquivo("CONTRATO - PNCP") == "CONTRATO - PNCP.pdf"
    assert anexos._nome_arquivo("a/b:c.pdf").endswith(".pdf")
    assert "/" not in anexos._nome_arquivo("a/b/c")
    assert anexos._nome_arquivo("") == "anexo.pdf"


async def test_folha_sem_anexo():
    """Folha e sem_anexo: lista vazia sem tocar no portal."""
    async with _client(make_portal()) as cli:
        # folha nao esta em _SECOES_ANEXO no endpoint, mas a funcao trata sem_anexo
        lst = await anexos.listar_anexos("senadorcanedo", "folha", {"id": "1"}, client=cli)
    assert lst == []


# --------------------------------------------------------------------------- #
# Endpoints HTTP (FastAPI TestClient) — headers e mapeamento de erro
# --------------------------------------------------------------------------- #

from fastapi.testclient import TestClient  # noqa: E402

from busca_go.api import app  # noqa: E402
from busca_go.db import DB  # noqa: E402
from busca_go.nucleo import casos as casos_module  # noqa: E402
from busca_go.nucleo import evidencia as evidencia_module  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """DB e DATA_DIR isolados por teste (mesmo motivo de `test_api_casos.py`):
    o lifespan de CADA `TestClient` roda `recuperar_jobs_interrompidos` e
    `evidencia.backfill_evidencias` -- sem isolamento, tocaria o
    `data/casos.db`/`data/casos/` reais em vez de um banco de teste."""
    banco_teste = DB(db_path=tmp_path / "casos-teste.db")
    monkeypatch.setattr(casos_module, "default_db", lambda: banco_teste)
    monkeypatch.setattr(evidencia_module.settings, "DATA_DIR", tmp_path)
    with TestClient(app) as c:
        yield c


def test_endpoint_lista_anexos_ok(client: TestClient, monkeypatch):
    async def fake(slug, secao, registro, client=None):
        assert registro == {"id": "1", "numero": "0343/26", "ano": "2026"}
        return [{"rotulo": "CONTRATO - PNCP", "ref": "tok"}]

    monkeypatch.setattr("busca_go.api.anexos.listar_anexos", fake)
    r = client.get("/api/anexos/senadorcanedo/contratos?id=1&numero=0343/26&ano=2026")
    assert r.status_code == 200
    assert r.json() == [{"rotulo": "CONTRATO - PNCP", "ref": "tok"}]


def test_endpoint_download_serve_pdf_limpo(client: TestClient, monkeypatch):
    async def fake(slug, secao, ref, client=None):
        return _PDF, "CONTRATO - PNCP.pdf", "application/pdf"

    monkeypatch.setattr("busca_go.api.anexos.baixar_anexo", fake)
    r = client.get("/api/anexos/senadorcanedo/contratos/download?ref=tok")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"] == 'attachment; filename="CONTRATO - PNCP.pdf"'
    assert r.content == _PDF
    # nunca vaza base64/JSON: o corpo e o binario cru
    assert r.content[:5] == b"%PDF-"


def test_endpoint_download_erro_portal_vira_502_json(client: TestClient, monkeypatch):
    async def fake(slug, secao, ref, client=None):
        raise anexos.AnexoError("O servidor de arquivos recusou o download (HTTP 403).")

    monkeypatch.setattr("busca_go.api.anexos.baixar_anexo", fake)
    r = client.get("/api/anexos/trindade/contratos/download?ref=tok")
    assert r.status_code == 502
    assert r.headers["content-type"].startswith("application/json")
    assert "error" in r.json()


def test_endpoint_ref_invalida_vira_404(client: TestClient, monkeypatch):
    async def fake(slug, secao, ref, client=None):
        raise anexos.AnexoIndisponivel("Referencia de anexo invalida ou expirada.")

    monkeypatch.setattr("busca_go.api.anexos.baixar_anexo", fake)
    r = client.get("/api/anexos/trindade/contratos/download?ref=xxx")
    assert r.status_code == 404


def test_endpoint_secao_sem_anexo_404(client: TestClient):
    r = client.get("/api/anexos/senadorcanedo/folha?id=1")
    assert r.status_code == 404
    r2 = client.get("/api/anexos/inexistente/contratos?id=1")
    assert r2.status_code == 404
