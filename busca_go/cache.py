"""Cache SQLite local para respostas do nucleogov.

Schema:
    kv(chave TEXT PRIMARY KEY, payload TEXT NOT NULL, cached_at REAL NOT NULL)

- chave = sha256(f"{slug}:{secao}:{args_estaveis_json}")
- payload = json da resposta completa (inclui o proprio cached_at)
- cached_at = timestamp UNIX da gravacao

TTL configuravel via Settings.CACHE_DAYS. Sem dependencia alem de stdlib.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from .config import settings


_SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (
    chave TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    cached_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS kv_cached_at_idx ON kv(cached_at);
"""


def _fingerprint(slug: str, secao: str, args: dict[str, Any]) -> str:
    """Hash estavel para identificar unicamente uma consulta."""
    args_canon = json.dumps(args or {}, sort_keys=True, ensure_ascii=False, default=str)
    raw = f"{slug}:{secao}:{args_canon}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class Cache:
    """Wrapper minimo sobre SQLite. Threadsafe via lock explicito."""

    def __init__(self, db_path: Path | None = None, ttl_days: int | None = None) -> None:
        self.db_path = Path(db_path) if db_path else settings.CACHE_DB
        self.ttl_days = ttl_days if ttl_days is not None else settings.CACHE_DAYS
        self.ttl_seconds = self.ttl_days * 86400
        self._lock = threading.Lock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=1.0)
        conn.row_factory = sqlite3.Row
        # Forca lock estilo DELETE (libera o arquivo imediatamente apos commit)
        # para nao segurar handles no Windows apos fechamento da conexao.
        try:
            conn.execute("PRAGMA journal_mode=DELETE")
        except sqlite3.DatabaseError:
            pass
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(_SCHEMA)
            conn.commit()

    def get(self, slug: str, secao: str, args: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """Retorna payload fresco (dentro do TTL) ou None se ausente/expirado."""
        chave = _fingerprint(slug, secao, args or {})
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT payload, cached_at FROM kv WHERE chave = ?", (chave,)).fetchone()
        if row is None:
            return None
        idade = time.time() - float(row["cached_at"])
        if idade > self.ttl_seconds:
            return None
        return json.loads(row["payload"])

    def put(self, slug: str, secao: str, args: dict[str, Any] | None, payload: dict[str, Any]) -> None:
        """Grava (ou sobrescreve) payload com cached_at = now()."""
        chave = _fingerprint(slug, secao, args or {})
        serialized = json.dumps(payload, ensure_ascii=False, default=str)
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO kv (chave, payload, cached_at) VALUES (?, ?, ?)",
                (chave, serialized, time.time()),
            )
            conn.commit()

    def purge_expired(self) -> int:
        """Remove entradas mais velhas que TTL. Retorna numero de linhas removidas."""
        limite = time.time() - self.ttl_seconds
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM kv WHERE cached_at < ?", (limite,))
            conn.commit()
        return cur.rowcount

    def clear(self) -> None:
        """Apaga todo o cache. Util em testes."""
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM kv")
            conn.commit()

    def close(self) -> None:
        """Fecha conexoes em cache. Idempotente. Use no fim de testes/scripts
        para liberar handles (problema comum em Windows)."""
        # sqlite3 connections sao criados por operacao via _connect,
        # mas se algum caller guardou referencia deve fechar manualmente.
        # Aqui nao temos handle persistente, entao este metodo e no-op seguro.
        return


# Singleton lazy — cria arquivo .db no primeiro uso. Reaproveita entre threads.
_default_cache: Cache | None = None


def default_cache() -> Cache:
    global _default_cache
    if _default_cache is None:
        _default_cache = Cache()
    return _default_cache
