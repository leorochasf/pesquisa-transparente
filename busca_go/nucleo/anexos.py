"""Download LAZY de anexos (PDFs) de contratos/licitacoes/dispensas NucleoGov.

Dois modelos DISTINTOS por (municipio, secao), confirmados ao vivo
(`AUDITORIA/10-viabilidade-download-pdf.md`); nao ha proxy generico unico:

- **Modo A — "detalhe_base64" (Senador Canedo).** O item da busca NAO tem PDF
  usavel (o campo `url`/`anexos` da 401 se acessado direto — armadilha). Para
  LISTAR os anexos de um registro: `POST /api` acao `<base>/listarAnexos` com o
  id/numero/anobase do registro. Para BAIXAR: `POST /api` acao
  `<base>/downloadAnexo` REENVIANDO o item do anexo -> o portal responde
  `{"k1":{"anexo":"<PDF em base64>"}}`; decodifica-se o base64. (`listarAditivos`
  foi deliberadamente NAO usado — ver `_listar_modo_a`.)

- **Modo B — "embutido_url_assinada" (Trindade).** O item de `busca_avancada` ja
  traz `anexos:[{id,titulo,download_url}]`, sendo `download_url` uma URL S3
  assinada (GET direto devolve o PDF) que EXPIRA em ~40min. Por isso tanto a
  listagem quanto o download REOBTEM o registro fresco (nova consulta ao portal)
  em vez de confiar numa URL possivelmente velha.

- **Modo C — url publica direta (Cristalina, Itumbiara, Sao Miguel do Araguaia;
  descoberto ao vivo nesta missao).** Estes portais listam anexos como no modo A
  (`listarAnexos`), mas o backend de arquivo e a Centi (`api.centi.com.br`), nao
  a NucleoGov: `downloadAnexo` responde "Acao nao encontrada" e o campo `url` de
  CADA anexo e um link PUBLICO direto (GET devolve o PDF). Tratado como fallback
  do download modo A (`_tentar_url_direta`): se `downloadAnexo` nao trouxer
  base64, tenta o GET direto no `url` do anexo. Em Senador Canedo esse mesmo `url`
  e a armadilha 401, entao o fallback so serve arquivo quando o GET responde 200.

Fluxo (decisao do orquestrador): a busca por entidade NAO carrega anexos; eles
sao listados sob demanda para UM registro e baixados por anexo especifico. O
backend serve o PDF limpo (`application/pdf`) — nunca expoe base64/JSON/URL
interna do portal ao navegador.

`ref` e um TOKEN OPACO (base64url de um JSON + assinatura HMAC) que carrega o
que o download precisa; o navegador nunca o interpreta, so o devolve ao
endpoint de download. A assinatura impede que um cliente forje um `ref` com
uma URL arbitraria (SSRF); alem disso, toda URL efetivamente buscada pelo
backend passa por allowlist de host (`_url_permitida`) como defesa em
profundidade.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
from typing import Any
from urllib.parse import urlsplit

import httpx

from ..config import settings
from ..municipios import Municipio, get as get_mun
from . import capacidades, entidade
from .routes import SecaoIndisponivel

_PAGE = entidade._PAGE
# Teto de paginas ao reobter um registro (modo B) por busca textual.
_MAX_SCAN_PAGINAS = entidade._MAX_PAGINAS

# Campos-id do anexo (modo B) usados para reencontra-lo apos reobter o registro.
_ANEXO_ID_KEYS = ("id", "midia_id", "chave")
# Campos de rotulo humano do anexo.
_ANEXO_ROTULO_KEYS = ("nome", "titulo", "descricao", "numero_contrato")


class AnexoError(RuntimeError):
    """Falha ao listar/baixar anexo (o endpoint traduz para 502)."""


class AnexoIndisponivel(AnexoError):
    """Anexo/registro nao encontrado ou secao sem anexo (o endpoint -> 404)."""


# --------------------------------------------------------------------------- #
# Token opaco (ref)
# --------------------------------------------------------------------------- #


def _assinar(raw: bytes) -> str:
    return hmac.new(settings.ANEXO_REF_SECRET.encode("utf-8"), raw, hashlib.sha256).hexdigest()


def _encode_ref(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    envelope = base64.urlsafe_b64encode(raw).decode("ascii")
    return f"{envelope}.{_assinar(raw)}"


def _decode_ref(ref: str) -> dict[str, Any]:
    try:
        envelope, ponto, assinatura = (ref or "").rpartition(".")
        if not ponto or not envelope or not assinatura:
            raise ValueError("ref sem assinatura")
        raw = base64.urlsafe_b64decode(envelope.encode("ascii"))
        if not hmac.compare_digest(_assinar(raw), assinatura):
            raise ValueError("assinatura invalida")
        dados = json.loads(raw)
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        raise AnexoIndisponivel("Referencia de anexo invalida ou expirada.") from exc
    if not isinstance(dados, dict) or dados.get("m") not in ("A", "B"):
        raise AnexoIndisponivel("Referencia de anexo invalida ou expirada.")
    return dados


# --------------------------------------------------------------------------- #
# Allowlist de host (defesa em profundidade contra SSRF)
# --------------------------------------------------------------------------- #

# Hosts de arquivo legitimos conhecidos (AUDITORIA/10-viabilidade-download-pdf.md).
# O host do proprio municipio (`mun.url_base`) e permitido a parte, por requisicao.
_HOST_CENTI = "api.centi.com.br"


def _host_permitido(host: str, host_municipio: str) -> bool:
    host = (host or "").lower()
    if not host:
        return False
    if host == host_municipio:
        return True
    if host == _HOST_CENTI:
        return True
    # S3 do NucleoGov: bucket sempre comeca com "nucleogov.s3" (ex.:
    # nucleogov.s3.us-east-2.amazonaws.com).
    return host.startswith("nucleogov.s3") and host.endswith(".amazonaws.com")


def _url_permitida(url: Any, mun: Municipio) -> str | None:
    """Valida esquema http(s) + host allowlisted. Devolve a URL ou None (recusa).

    Nao resolve DNS/IP (a checagem de IP privado ficaria cara e a allowlist de
    host explicita ja fecha o vetor: um `ref` forjado nao consegue apontar para
    um host fora dos 3 permitidos, entao nao ha bypass via redirecionamento de
    hostname arbitrario).
    """
    if not isinstance(url, str) or not url:
        return None
    try:
        partes = urlsplit(url)
    except ValueError:
        return None
    if partes.scheme not in ("http", "https"):
        return None
    host_municipio = (urlsplit(mun.url_base).hostname or "").lower()
    if not _host_permitido((partes.hostname or "").lower(), host_municipio):
        return None
    return url


# --------------------------------------------------------------------------- #
# Nome/rotulo/content-type
# --------------------------------------------------------------------------- #

_SANEA = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def _rotulo(item: dict[str, Any]) -> str:
    for k in _ANEXO_ROTULO_KEYS:
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return "anexo"


def _nome_arquivo(rotulo: str) -> str:
    """Rotulo -> nome de arquivo seguro terminando em .pdf."""
    base = _SANEA.sub(" ", rotulo or "anexo").strip() or "anexo"
    base = re.sub(r"\s+", " ", base)
    if not base.lower().endswith(".pdf"):
        base = f"{base}.pdf"
    return base


def _content_type(blob: bytes, header: str | None = None) -> str:
    if blob[:5] == b"%PDF-":
        return "application/pdf"
    if header:
        ct = header.split(";")[0].strip()
        if ct:
            return ct
    return "application/octet-stream"


# --------------------------------------------------------------------------- #
# Driver low-level: k1 cru (para downloadAnexo, que devolve {"anexo": b64})
# --------------------------------------------------------------------------- #


async def _post_multi_k1(
    client: httpx.AsyncClient, url_base: str, acao: str, params: dict[str, Any]
) -> Any:
    """POST /api multi_request devolvendo o bloco k1 CRU (nao {total,dados}).

    `downloadAnexo` responde `{"k1":{"anexo":"<b64>"}}` — um formato diferente do
    `{total,dados}` que `entidade._multi` normaliza; aqui devolvemos o k1 como
    veio para extrair o base64.
    """
    corpo = {
        "multi_request": "true",
        "params": json.dumps({"k1": {"acao": acao, "limit": "0, 50", **params}}),
    }
    try:
        resp = await entidade._post_com_retry(client, f"{url_base}/api", corpo)
    except httpx.HTTPError as exc:
        raise AnexoError(entidade._msg_falha_rede(exc)) from exc
    if resp.status_code != 200:
        raise AnexoError(f"O portal recusou o download (HTTP {resp.status_code}).")
    try:
        data = json.loads(resp.content)
    except (json.JSONDecodeError, ValueError) as exc:
        raise AnexoError(f"Resposta invalida do portal ao baixar o anexo: {exc}") from exc
    return data.get("k1") if isinstance(data, dict) else None


# --------------------------------------------------------------------------- #
# Modo B: reobter o registro fresco por busca textual (numero/id)
# --------------------------------------------------------------------------- #


async def _reobter_registro_b(
    client: httpx.AsyncClient,
    url_base: str,
    acao_busca: str | None,
    campo_busca: str | None,
    rid: str,
    numero: str,
) -> dict[str, Any] | None:
    """Reobtem o registro fresco (com `anexos` de URL nao expirada) por busca.

    Casa pelo id do registro (`id`/`contrato_id`/`licitacao_id`) entre os
    resultados da busca pelo numero. Retorna None se nao houver canal de busca,
    nem numero/id, ou o registro nao for reencontrado.
    """
    if not (acao_busca and campo_busca):
        return None
    termo = (numero or rid or "").strip()
    if not termo:
        return None
    rid = str(rid or "")
    offset = 0
    paginas = 0
    while paginas < _MAX_SCAN_PAGINAS:
        pg = await entidade._multi(client, url_base, acao_busca, {campo_busca: termo}, offset, _PAGE)
        dados = pg["dados"]
        for it in dados:
            ident = str(it.get("id") or it.get("contrato_id") or it.get("licitacao_id") or "")
            if rid and ident == rid:
                return it
        # Sem id para casar E resultado unico: assume o unico registro.
        if not rid and pg["total"] == 1 and len(dados) == 1:
            return dados[0]
        if not dados:
            break
        offset += _PAGE
        paginas += 1
        if pg["total"] and offset >= pg["total"]:
            break
    return None


def _anexos_b_para_refs(secao: str, cap: capacidades.Capacidade, registro: dict[str, Any],
                        reg: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for a in reg.get("anexos") or []:
        if not isinstance(a, dict):
            continue
        aid = ""
        for k in _ANEXO_ID_KEYS:
            if a.get(k):
                aid = str(a[k])
                break
        rotulo = _rotulo(a)
        ref = _encode_ref(
            {
                "m": "B",
                "s": secao,
                "rid": str(registro.get("id") or ""),
                "numero": str(registro.get("numero") or ""),
                "aid": aid,
                "url": a.get("download_url") or "",
                "nome": rotulo,
            }
        )
        out.append({"rotulo": rotulo, "ref": ref})
    return out


# --------------------------------------------------------------------------- #
# Modo A: listarAnexos (+ listarAditivos) e refs de download por base64
# --------------------------------------------------------------------------- #


def _params_listar_a(cap: capacidades.Capacidade, registro: dict[str, Any]) -> dict[str, str] | None:
    rid = str(registro.get("id") or "").strip()
    if not rid:
        return None
    chave = capacidades.chave_registro_anexo(cap)  # "contrato" | "licitacao"
    params = {chave: rid}
    ano = str(registro.get("ano") or "").strip()
    if ano:
        params["anobase"] = ano
    numero = str(registro.get("numero") or "").strip()
    if numero and chave == "contrato":
        params["numero_contrato"] = numero
    return params


async def _listar_modo_a(
    client: httpx.AsyncClient,
    mun: Municipio,
    secao: str,
    cap: capacidades.Capacidade,
    registro: dict[str, Any],
) -> list[dict[str, str]]:
    params = _params_listar_a(cap, registro)
    if params is None:
        return []
    acoes = capacidades.acoes_anexo(cap)
    pg = await entidade._multi(client, mun.url_base, acoes["listar_anexos"], params, 0, _PAGE)
    out: list[dict[str, str]] = []
    for it in pg["dados"]:
        if isinstance(it, dict):
            out.append({"rotulo": _rotulo(it), "ref": _encode_ref({"m": "A", "acao": acoes["download"], "item": it})})
    # NOTA sobre aditivos (verificado ao vivo nesta missao): NAO se mescla
    # `listarAditivos` aqui. Em Senador Canedo esse acao (a) NAO filtra pelo
    # contrato — sem `numero_contrato` devolve a lista GLOBAL de ~1125 aditivos,
    # anexando documentos de OUTROS contratos — e (b) devolve METADADOS de
    # aditivo (label/numero/contratado), nao itens de anexo baixaveis (sem
    # chave/url). O PDF do aditivo, quando existe, aparece: em Trindade dentro do
    # array `anexos` do proprio contrato (modo B, ja coberto); em Senador Canedo
    # exigiria um fluxo proprio nao confirmado. Preferir a verdade a um merge
    # incorreto.
    return out


async def _listar_modo_b(
    client: httpx.AsyncClient,
    mun: Municipio,
    secao: str,
    cap: capacidades.Capacidade,
    registro: dict[str, Any],
) -> list[dict[str, str]]:
    reg = await _reobter_registro_b(
        client, mun.url_base, cap.acao_busca, cap.campo_busca,
        str(registro.get("id") or ""), str(registro.get("numero") or ""),
    )
    if reg is None:
        return []
    return _anexos_b_para_refs(secao, cap, registro, reg)


# --------------------------------------------------------------------------- #
# API publica
# --------------------------------------------------------------------------- #


async def listar_anexos(
    slug: str,
    secao: str,
    registro: dict[str, Any],
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, str]]:
    """Lista os anexos de UM registro: `[{rotulo, ref}]` (ref = token opaco).

    Args:
        slug: municipio.
        secao: 'contratos' | 'licitacoes' | 'dispensas'.
        registro: identificadores {'id','numero','ano'} preservados pela busca
            (`entidade._normalizar_item` -> campo `ref_registro`).
        client: httpx.AsyncClient injetavel (teste); se None, cria/fecha o proprio.

    Raises:
        KeyError: municipio nao cadastrado.
        SecaoIndisponivel: secao inexistente no portal.
        AnexoError/PortalError: falha de portal.
    """
    mun = get_mun(slug)
    cap = capacidades.resolver(slug, secao)
    fechar = client is None
    cli = client or entidade._novo_client()
    try:
        modo = cap.modo_anexo
        if modo == "sem_anexo":
            return []
        if modo == "detalhe_base64":
            return await _listar_modo_a(cli, mun, secao, cap, registro)
        if modo == "embutido_url_assinada":
            return await _listar_modo_b(cli, mun, secao, cap, registro)
        # nao_confirmado -> DETECTA: tenta modo A (listarAnexos direto); se vazio,
        # tenta modo B (reobter registro e ler o array `anexos`).
        via_a = await _listar_modo_a(cli, mun, secao, cap, registro)
        if via_a:
            return via_a
        return await _listar_modo_b(cli, mun, secao, cap, registro)
    finally:
        if fechar:
            await cli.aclose()


async def _baixar_modo_a(
    client: httpx.AsyncClient, mun: Municipio, dados: dict[str, Any]
) -> tuple[bytes, str, str]:
    item = dados.get("item")
    acao = dados.get("acao")
    if not isinstance(item, dict) or not acao:
        raise AnexoIndisponivel("Referencia de anexo invalida ou expirada.")
    k1 = await _post_multi_k1(client, mun.url_base, acao, item)
    b64: str | None = None
    if isinstance(k1, dict):
        if isinstance(k1.get("anexo"), str):
            b64 = k1["anexo"]
        else:  # as vezes: {"<chave>":{"anexo": "<b64>"}}
            for v in k1.values():
                if isinstance(v, dict) and isinstance(v.get("anexo"), str):
                    b64 = v["anexo"]
                    break
    if not b64:
        # Fallback modo C (Centi: cristalina/itumbiara/saomiguel). Nesses portais
        # `downloadAnexo` nao existe ("Acao nao encontrada"), mas o proprio item
        # do anexo traz `url` = link publico direto (GET devolve o PDF). Em
        # Senador Canedo a `url` e a ARMADILHA que da 401 -> o GET falha e caimos
        # em AnexoIndisponivel, sem servir lixo.
        blob = await _tentar_url_direta(client, item.get("url"), mun)
        if blob is not None:
            return blob, _nome_arquivo(_rotulo(item)), _content_type(blob)
        raise AnexoIndisponivel("O portal nao retornou o arquivo deste anexo.")
    try:
        blob = base64.b64decode(b64)
    except (binascii.Error, ValueError) as exc:
        raise AnexoError(f"Anexo com conteudo invalido: {exc}") from exc
    return blob, _nome_arquivo(_rotulo(item)), _content_type(blob)


async def _tentar_url_direta(client: httpx.AsyncClient, url: Any, mun: Municipio) -> bytes | None:
    """GET direto no `url` do anexo (modo C/Centi). None se nao for arquivo servivel.

    `url` vem do `ref` (nao mais forjavel, ver `_decode_ref`), mas passa tambem
    pela allowlist de host (`_url_permitida`) como defesa em profundidade.
    Aceita so 200 com corpo que NAO parece pagina de erro (HTML/JSON) — a
    armadilha de Senador Canedo (401) e paginas de erro caem para None.
    """
    url = _url_permitida(url, mun)
    if url is None:
        return None
    try:
        resp = await client.get(url)
    except httpx.HTTPError:
        return None
    if resp.status_code != 200:
        return None
    corpo = resp.content
    if len(corpo) <= 4 or corpo[:1] in (b"<", b"{"):
        return None
    return corpo


async def _baixar_modo_b(
    client: httpx.AsyncClient, mun: Municipio, secao: str, dados: dict[str, Any]
) -> tuple[bytes, str, str]:
    # Reobtem fresco (URL S3 expira ~40min); fallback: URL capturada na listagem.
    cap = capacidades.resolver(mun.slug, secao)
    url = ""
    reg = await _reobter_registro_b(
        client, mun.url_base, cap.acao_busca, cap.campo_busca,
        str(dados.get("rid") or ""), str(dados.get("numero") or ""),
    )
    if reg:
        aid = str(dados.get("aid") or "")
        for a in reg.get("anexos") or []:
            if not isinstance(a, dict):
                continue
            cand = ""
            for k in _ANEXO_ID_KEYS:
                if a.get(k):
                    cand = str(a[k])
                    break
            if aid and cand == aid and a.get("download_url"):
                url = a["download_url"]
                break
    if not url:
        url = dados.get("url") or ""  # fallback: link da listagem (pode ter expirado)
    url = _url_permitida(url, mun)
    if not url:
        raise AnexoIndisponivel(
            "Nao foi possivel localizar o arquivo do anexo (o registro pode ter mudado)."
        )
    try:
        resp = await client.get(url)
    except httpx.HTTPError as exc:
        raise AnexoError(entidade._msg_falha_rede(exc)) from exc
    if resp.status_code != 200:
        raise AnexoError(
            f"O servidor de arquivos recusou o download (HTTP {resp.status_code}); "
            "o link do anexo pode ter expirado."
        )
    blob = resp.content
    ctype = _content_type(blob, resp.headers.get("content-type"))
    return blob, _nome_arquivo(dados.get("nome") or "anexo"), ctype


async def baixar_anexo(
    slug: str,
    secao: str,
    ref: str,
    client: httpx.AsyncClient | None = None,
) -> tuple[bytes, str, str]:
    """Baixa UM anexo pelo token opaco. Retorna (bytes, nome_arquivo, content_type).

    Modo A: `downloadAnexo` + decode base64. Modo B: reobtem o registro fresco,
    localiza o anexo e faz GET na URL assinada (fallback: URL do proprio token).

    Raises:
        KeyError: municipio nao cadastrado.
        AnexoIndisponivel: ref invalida ou anexo/registro nao encontrado (-> 404).
        AnexoError/PortalError: falha de portal (-> 502).
    """
    mun = get_mun(slug)
    dados = _decode_ref(ref)
    fechar = client is None
    cli = client or entidade._novo_client()
    try:
        if dados.get("m") == "A":
            return await _baixar_modo_a(cli, mun, dados)
        return await _baixar_modo_b(cli, mun, secao, dados)
    finally:
        if fechar:
            await cli.aclose()


__all__ = ["listar_anexos", "baixar_anexo", "AnexoError", "AnexoIndisponivel", "SecaoIndisponivel"]
