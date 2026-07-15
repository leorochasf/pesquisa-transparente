"""CLI do busca-transparencia-goias.

Uso:
    busca-go municipios
    busca-go secoes <slug>
    busca-go <slug> <secao> [--ano YYYY] [--cnpj X]
    busca-go config
    busca-go cache {clear,purge}

Saida padrao: JSON. Use --human para tabela formatada.

Aviso: comandos que navegam (secoes, busca) exigem Playwright + Chromium.
Rode `playwright install chromium` antes do primeiro uso.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from typing import Any

from .cache import Cache, default_cache
from .config import settings
from .municipios import get as get_mun
from .nucleo.client import NucleoClient
from .nucleo.routes import SecaoIndisponivel, secoes_disponiveis


# ---------- helpers de saida ----------


def _to_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def _to_human_items(items: list[dict[str, Any]]) -> str:
    """Tabela simples para stdout. Sem dependencia de rich."""
    if not items:
        return "(sem items)"
    cols = ["titulo", "data", "valor", "link"]
    widths = {c: max(len(c), max((len(str(i.get(c, "")) or "") for i in items))) for c in cols}
    head = " | ".join(c.ljust(widths[c]) for c in cols)
    sep = "-+-".join("-" * widths[c] for c in cols)
    rows = [
        " | ".join(str(i.get(c, "") or "").ljust(widths[c]) for c in cols)
        for i in items
    ]
    return "\n".join([head, sep, *rows])


def _ts(epoch: float | None) -> str:
    if not epoch:
        return "-"
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


# ---------- comandos ----------


def cmd_municipios(_args: argparse.Namespace) -> int:
    snap = NucleoClient.listar_municipios()
    print(_to_json(snap))
    return 0


def cmd_config(_args: argparse.Namespace) -> int:
    print(_to_json({
        "cache_db": str(settings.CACHE_DB),
        "cache_days": settings.CACHE_DAYS,
        "headless": settings.HEADLESS,
        "timeout_ms": settings.TIMEOUT_MS,
    }))
    return 0


def cmd_cache(args: argparse.Namespace, cache: Cache) -> int:
    if args.action == "clear":
        cache.clear()
        print(json.dumps({"ok": True, "action": "clear"}))
    elif args.action == "purge":
        removed = cache.purge_expired()
        print(json.dumps({"ok": True, "action": "purge", "removed": removed}))
    else:  # pragma: no cover
        print(json.dumps({"ok": False, "error": f"acao desconhecida: {args.action}"}))
        return 2
    return 0


def cmd_web(_args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run("busca_go.api:app", host="127.0.0.1", port=settings.PORT)
    return 0


def _run_secoes(slug: str, human: bool) -> int:
    """Lista as secoes disponiveis do municipio a partir da tabela estatica
    de rotas reais (sem navegar/scrapear menu)."""
    try:
        get_mun(slug)
    except KeyError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    secs = secoes_disponiveis(slug)
    if human:
        print(f"{slug}: {', '.join(secs) or '(nenhuma)'}")
    else:
        print(_to_json({"slug": slug, "secoes": secs}))
    return 0


async def _run_busca(slug: str, secao: str, filtros: dict[str, Any], human: bool) -> int:
    async with NucleoClient() as c:
        try:
            result = await c.fetch_section(slug, secao, **filtros)
        except SecaoIndisponivel as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
            return 3
        except KeyError as exc:
            print(json.dumps({"ok": False, "error": str(exc)}))
            return 2
        except Exception as exc:
            print(json.dumps({"ok": False, "error": f"falha ao buscar: {exc}"}))
            return 1
    if human:
        print(f"slug:        {slug}")
        print(f"secao:       {secao}")
        print(f"filtros:     {filtros or '-'} ")
        print(f"plataforma:  {result['plataforma']}")
        print(f"source_url:  {result['source_url']}")
        print(f"cached:      {result['cached']}  cached_at: {_ts(result['cached_at'])}")
        print(f"items:       {len(result['items'])}")
        print()
        print(_to_human_items(result["items"]))
    else:
        print(_to_json(result))
    return 0


# ---------- argparse ----------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="busca-go",
        description="Consulta de transparencia publica de municipios goianos (portal nucleogov).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("municipios", help="Lista os municipios cadastrados")
    sub.add_parser("config", help="Mostra configuracao ativa")
    sub.add_parser("web", help="Sobe o servidor HTTP (FastAPI/uvicorn) local")

    p_secoes = sub.add_parser("secoes", help="Descobre secoes de um municipio")
    p_secoes.add_argument("slug", help="Slug do municipio (ex.: senadorcanedo)")
    p_secoes.add_argument("--human", action="store_true", help="Saida em texto formatado")

    p_busca = sub.add_parser("buscar", aliases=["b"], help="Busca itens de uma secao")
    p_busca.add_argument("slug", help="Slug do municipio (ex.: senadorcanedo)")
    p_busca.add_argument("secao", help="Slug da secao (ex.: licitacoes)")
    p_busca.add_argument("--ano", type=int, help="Filtro de ano")
    p_busca.add_argument("--cnpj", help="Filtro de CNPJ")
    p_busca.add_argument("--modalidade", help="Filtro de modalidade (licitacoes)")
    p_busca.add_argument("--numero", help="Filtro de numero (contratos)")
    p_busca.add_argument("--credor", help="Filtro de credor (despesas)")
    p_busca.add_argument("--human", action="store_true", help="Saida em texto formatado")

    p_cache = sub.add_parser("cache", help="Operacoes no cache local")
    p_cache.add_argument("action", choices=["clear", "purge"], help="Acao: clear (limpa tudo) ou purge (remove expirados)")

    p.add_argument("--human", action="store_true", help="(padrao global) Saida em texto formatado")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cache = default_cache()

    if args.cmd == "municipios":
        return cmd_municipios(args)
    if args.cmd == "config":
        return cmd_config(args)
    if args.cmd == "web":
        return cmd_web(args)
    if args.cmd == "cache":
        return cmd_cache(args, cache)
    if args.cmd == "secoes":
        return _run_secoes(args.slug, args.human)
    if args.cmd in ("buscar", "b"):
        filtros: dict[str, Any] = {}
        for k in ("ano", "cnpj", "modalidade", "numero", "credor"):
            v = getattr(args, k, None)
            if v is not None:
                filtros[k] = v
        return asyncio.run(_run_busca(args.slug, args.secao, filtros, args.human))

    print(json.dumps({"ok": False, "error": f"comando desconhecido: {args.cmd}"}))
    return 2


if __name__ == "__main__":
    sys.exit(main())
