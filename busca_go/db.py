"""SQLite de persistencia dos casos/dossies (schema do blueprint P2, doc
AUDITORIA/refatoracao/04-blueprint.md §4). Banco SEPARADO do cache de
respostas do portal (`busca_go/cache.py`) -- TTL de cache nao se mistura com
dado permanente do caso. Banco em `data/casos.db` (`Settings.CASOS_DB`).
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from .config import settings

_SCHEMA_CASOS_ITENS = """
CREATE TABLE IF NOT EXISTS casos (
    id TEXT PRIMARY KEY,
    titulo TEXT NOT NULL,
    tipo TEXT NOT NULL,
    alvos_json TEXT NOT NULL,
    municipios_json TEXT NOT NULL,
    criado_em REAL NOT NULL,
    atualizado_em REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS itens (
    id TEXT PRIMARY KEY,
    caso_id TEXT NOT NULL REFERENCES casos(id),
    municipio TEXT NOT NULL,
    secao TEXT NOT NULL,
    titulo TEXT,
    documento TEXT,
    valor TEXT,
    data TEXT,
    ref_registro_json TEXT,
    raw_json TEXT NOT NULL,
    origem_json TEXT,
    criado_em REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS itens_caso_idx ON itens(caso_id);
"""

# `id` (evidencia_id, "ev_NNNNNN") e sequencial POR CASO (contador do
# manifesto reinicia em cada caso -- ver `nucleo/evidencia.py::registrar_evidencia`),
# entao a PK precisa ser composta (caso_id, id): 2 casos diferentes podem
# gerar o MESMO "ev_000001" sem colidir entre si. `CREATE TABLE`/`CREATE
# INDEX` extraidos em constantes proprias (nao so dentro do schema completo)
# porque `_migrar_evidencias_pk_composta` tambem precisa roda-las
# individualmente via `execute` (nunca `executescript` -- ver docstring
# da migracao).
_CREATE_EVIDENCIAS = """
CREATE TABLE IF NOT EXISTS evidencias (
    id TEXT NOT NULL,
    caso_id TEXT NOT NULL REFERENCES casos(id),
    item_id TEXT REFERENCES itens(id),
    tipo TEXT NOT NULL,
    caminho_local TEXT NOT NULL,
    url_origem TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    bytes INTEGER,
    content_type TEXT,
    coletado_em REAL NOT NULL,
    PRIMARY KEY (caso_id, id)
)
"""
_CREATE_EVIDENCIAS_IDX = "CREATE INDEX IF NOT EXISTS evidencias_caso_idx ON evidencias(caso_id)"

_SCHEMA_ANOTACOES_BUSCAS = """
CREATE TABLE IF NOT EXISTS anotacoes (
    id TEXT PRIMARY KEY,
    caso_id TEXT NOT NULL REFERENCES casos(id),
    item_id TEXT REFERENCES itens(id),
    tag TEXT,
    texto TEXT,
    criado_em REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS anotacoes_caso_idx ON anotacoes(caso_id);

CREATE TABLE IF NOT EXISTS buscas (
    id TEXT PRIMARY KEY,
    caso_id TEXT NOT NULL REFERENCES casos(id),
    parametros_json TEXT NOT NULL,
    resultado_resumo_json TEXT,
    status TEXT NOT NULL,
    progresso_json TEXT,
    iniciada_em REAL,
    concluida_em REAL
);
CREATE INDEX IF NOT EXISTS buscas_caso_idx ON buscas(caso_id);
"""

_SCHEMA = (
    _SCHEMA_CASOS_ITENS
    + _CREATE_EVIDENCIAS + ";\n"
    + _CREATE_EVIDENCIAS_IDX + ";\n"
    + _SCHEMA_ANOTACOES_BUSCAS
)


class DB:
    """Wrapper minimo sobre SQLite. Mesmo padrao de `cache.py`: sem handle de
    conexao persistente (uma conexao por operacao, protegida por lock) --
    evita conexao presa no Windows quando o processo e encerrado no meio."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else settings.CASOS_DB
        self._lock = threading.Lock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        # DELETE (nao WAL): libera o arquivo imediatamente apos commit, evita
        # handle preso no Windows -- mesma escolha de journal de `cache.py`.
        try:
            conn.execute("PRAGMA journal_mode=DELETE")
        except sqlite3.DatabaseError:
            pass
        return conn

    def _init_schema(self) -> None:
        with self._lock, self.connect() as conn:
            conn.executescript(_SCHEMA)
            self._migrar_evidencias_pk_composta(conn)
            conn.commit()

    def _migrar_evidencias_pk_composta(self, conn: sqlite3.Connection) -> None:
        """Migracao unica (W2-F1): bancos criados antes desta correcao tem
        `evidencias.id TEXT PRIMARY KEY` (coluna unica) -- `CREATE TABLE IF
        NOT EXISTS` do `_SCHEMA` acima nao adianta pra tabela ja existente.
        `evidencia_id` (ev_NNNNNN) e sequencial POR CASO, entao 2 casos
        podem gerar o mesmo id; recria a tabela com PK composta
        `(caso_id, id)`, preservando as linhas existentes. Idempotente:
        so roda se a PK antiga (coluna unica) ainda estiver no lugar.

        W2FIX-F1: todo o rename->recria->copia->dropa roda dentro de UM
        `BEGIN`/`commit()` explicito -- sem isso (a versao anterior usava
        `executescript`, que da COMMIT implicito da transacao pendente antes
        de rodar), o DDL do sqlite3 comita sozinho passo a passo mesmo sem
        `commit()` (confirmado empiricamente); um crash no meio deixava
        `evidencias` vazia com os dados presos em `evidencias_pre_pk_composta`
        pra sempre. Com o `BEGIN` explicito, um crash antes do `commit()` faz
        o SQLite reverter TUDO no proximo `connect()` -- nunca ha estado
        parcial visivel.

        W2FIX-F2: o indice `evidencias_caso_idx` e recriado DEPOIS do `DROP
        TABLE` da tabela renomeada -- `ALTER TABLE RENAME` leva o indice
        antigo junto (mesmo nome); recria-lo ANTES do drop seria um no-op
        (nome ja em uso), e so apareceria no boot seguinte.
        """
        info = conn.execute("PRAGMA table_info(evidencias)").fetchall()
        pk_cols = [row[1] for row in sorted(info, key=lambda r: r[5]) if row[5] > 0]
        if not info or pk_cols == ["caso_id", "id"]:
            return  # tabela nova (CREATE TABLE ja cuidou) ou ja migrada
        conn.execute("BEGIN")
        conn.execute("ALTER TABLE evidencias RENAME TO evidencias_pre_pk_composta")
        conn.execute(_CREATE_EVIDENCIAS)
        conn.execute(
            """INSERT INTO evidencias
               (id, caso_id, item_id, tipo, caminho_local, url_origem,
                sha256, bytes, content_type, coletado_em)
               SELECT id, caso_id, item_id, tipo, caminho_local, url_origem,
                      sha256, bytes, content_type, coletado_em
               FROM evidencias_pre_pk_composta"""
        )
        conn.execute("DROP TABLE evidencias_pre_pk_composta")
        conn.execute(_CREATE_EVIDENCIAS_IDX)
        conn.commit()


# Singleton lazy — mesmo padrao de `cache.default_cache()`.
_default_db: DB | None = None


def default_db() -> DB:
    global _default_db
    if _default_db is None:
        _default_db = DB()
    return _default_db


__all__ = ["DB", "default_db"]
