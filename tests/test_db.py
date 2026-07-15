"""Testes de `busca_go/db.py`: schema + migracao (W2-F1).

`evidencia_id` (ev_NNNNNN) e sequencial POR CASO (o contador do manifesto
reinicia em cada caso) -- a PK de `evidencias` precisa ser composta
(caso_id, id), senao 2 casos diferentes com o mesmo `ev_000001` colidem via
`INSERT OR IGNORE` e um deles nunca e indexado (bug descoberto ao vivo nesta
missao)."""

from __future__ import annotations

import sqlite3

from busca_go.db import DB

_SCHEMA_ANTIGO = """
CREATE TABLE casos (
    id TEXT PRIMARY KEY, titulo TEXT NOT NULL, tipo TEXT NOT NULL,
    alvos_json TEXT NOT NULL, municipios_json TEXT NOT NULL,
    criado_em REAL NOT NULL, atualizado_em REAL NOT NULL
);
CREATE TABLE itens (
    id TEXT PRIMARY KEY, caso_id TEXT NOT NULL REFERENCES casos(id),
    municipio TEXT NOT NULL, secao TEXT NOT NULL, titulo TEXT,
    documento TEXT, valor TEXT, data TEXT, ref_registro_json TEXT,
    raw_json TEXT NOT NULL, origem_json TEXT, criado_em REAL NOT NULL
);
CREATE TABLE evidencias (
    id TEXT PRIMARY KEY,
    caso_id TEXT NOT NULL REFERENCES casos(id),
    item_id TEXT REFERENCES itens(id),
    tipo TEXT NOT NULL,
    caminho_local TEXT NOT NULL,
    url_origem TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    bytes INTEGER,
    content_type TEXT,
    coletado_em REAL NOT NULL
);
CREATE INDEX evidencias_caso_idx ON evidencias(caso_id);
"""


def _criar_banco_schema_antigo(db_path, *, casos=(("caso_a", "sha-a"),)):
    """Constroi um `casos.db` no formato PRE-W2-FIX (evidencias.id TEXT
    PRIMARY KEY, coluna unica) com 1 caso + 1 evidencia por entrada de
    `casos` -- ponto de partida das migracoes testadas abaixo."""
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA_ANTIGO)
    for i, (caso_id, sha) in enumerate(casos, start=1):
        conn.execute(f"INSERT INTO casos VALUES ('{caso_id}','C','livre','{{}}','[]',1,1)")
        conn.execute(
            "INSERT INTO evidencias (id, caso_id, tipo, caminho_local, url_origem, sha256, bytes, content_type, coletado_em) "
            f"VALUES ('ev_00000{i}','{caso_id}','pdf','a.pdf','https://x','{sha}',1,'application/pdf',1.0)"
        )
    conn.commit()
    conn.close()


def test_schema_novo_ja_nasce_com_pk_composta(tmp_path):
    db = DB(db_path=tmp_path / "casos.db")
    with db._lock, db.connect() as conn:
        info = conn.execute("PRAGMA table_info(evidencias)").fetchall()
    pk_cols = [row[1] for row in sorted(info, key=lambda r: r[5]) if row[5] > 0]
    assert pk_cols == ["caso_id", "id"]


def test_migra_schema_antigo_com_pk_unica_para_pk_composta_sem_perder_dados(tmp_path):
    """Simula um `casos.db` criado ANTES desta correcao (id TEXT PRIMARY KEY,
    coluna unica) e confirma que abrir com `DB(...)` migra para a PK composta
    preservando a linha existente."""
    db_path = tmp_path / "casos-antigo.db"
    _criar_banco_schema_antigo(db_path)

    db = DB(db_path=db_path)  # __init__ chama _init_schema -> migra
    with db._lock, db.connect() as conn2:
        info = conn2.execute("PRAGMA table_info(evidencias)").fetchall()
        pk_cols = [row[1] for row in sorted(info, key=lambda r: r[5]) if row[5] > 0]
        rows = conn2.execute("SELECT id, caso_id, sha256 FROM evidencias").fetchall()
    assert pk_cols == ["caso_id", "id"]
    assert len(rows) == 1  # a linha pre-existente nao se perdeu na migracao
    assert rows[0]["sha256"] == "sha-a"


def test_migracao_recria_evidencias_caso_idx_no_mesmo_boot(tmp_path):
    """W2FIX-F2: `evidencias_caso_idx` nao pode sumir ate o boot seguinte --
    `ALTER TABLE RENAME` leva o indice antigo junto (mesmo nome); a migracao
    tem que recria-lo DEPOIS do DROP da tabela renomeada, no MESMO boot."""
    db_path = tmp_path / "casos-antigo.db"
    _criar_banco_schema_antigo(db_path)

    db = DB(db_path=db_path)
    with db._lock, db.connect() as conn:
        idx = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='evidencias' "
            "AND name='evidencias_caso_idx'"
        ).fetchone()
    assert idx is not None


def test_migracao_sobrevive_a_crash_no_meio_sem_perder_nem_travar_dados(tmp_path):
    """W2FIX-F1: reproduz o crash que a revisao encontrou -- processo morre
    ENTRE o rename e o commit da migracao (sem chegar no `commit()` final).
    Antes da correcao isso deixava `evidencias` vazia e os dados presos em
    `evidencias_pre_pk_composta` para sempre (a migracao antiga usava
    `executescript`, que comita o rename sozinho). Com o `BEGIN` explicito,
    fechar a conexao sem commit deve reverter TUDO -- o proximo `DB(...)`
    encontra o banco intacto (schema antigo, dado intacto) e migra
    normalmente, sem tabela-sobra nem perda."""
    db_path = tmp_path / "casos-antigo.db"
    _criar_banco_schema_antigo(db_path, casos=(("caso_a", "sha-a"), ("caso_b", "sha-b")))

    # Reproduz o exato meio da migracao (rename -> cria -> copia), depois
    # "morre" (fecha sem commit) -- mesmo cenario que o revisor simulou.
    conn = sqlite3.connect(db_path)
    conn.execute("BEGIN")
    conn.execute("ALTER TABLE evidencias RENAME TO evidencias_pre_pk_composta")
    conn.execute(
        """CREATE TABLE evidencias (
            id TEXT NOT NULL, caso_id TEXT NOT NULL REFERENCES casos(id),
            item_id TEXT REFERENCES itens(id), tipo TEXT NOT NULL,
            caminho_local TEXT NOT NULL, url_origem TEXT NOT NULL,
            sha256 TEXT NOT NULL, bytes INTEGER, content_type TEXT,
            coletado_em REAL NOT NULL, PRIMARY KEY (caso_id, id)
        )"""
    )
    conn.execute(
        "INSERT INTO evidencias (id, caso_id, tipo, caminho_local, url_origem, sha256, bytes, content_type, coletado_em) "
        "SELECT id, caso_id, tipo, caminho_local, url_origem, sha256, bytes, content_type, coletado_em "
        "FROM evidencias_pre_pk_composta"
    )
    conn.close()  # "crash": nunca chega no commit() nem no DROP/CREATE INDEX final

    # Verifica que o crash nao deixou nada visivel a meio caminho: reabrindo
    # com sqlite puro (sem passar por `DB`), o banco tem que estar como se
    # a migracao nunca tivesse comecado.
    conn_cru = sqlite3.connect(db_path)
    tabelas = {r[0] for r in conn_cru.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "evidencias_pre_pk_composta" not in tabelas  # nao ficou tabela-sobra
    linhas_antes = conn_cru.execute("SELECT COUNT(*) FROM evidencias").fetchone()[0]
    conn_cru.close()
    assert linhas_antes == 2  # dado original intacto, nao sumiu

    # O proximo boot completa a migracao normalmente, sem perder nada.
    db = DB(db_path=db_path)
    with db._lock, db.connect() as conn2:
        info = conn2.execute("PRAGMA table_info(evidencias)").fetchall()
        pk_cols = [row[1] for row in sorted(info, key=lambda r: r[5]) if row[5] > 0]
        rows = conn2.execute("SELECT caso_id, sha256 FROM evidencias ORDER BY caso_id").fetchall()
        tabelas2 = {r[0] for r in conn2.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert pk_cols == ["caso_id", "id"]
    assert {r["caso_id"]: r["sha256"] for r in rows} == {"caso_a": "sha-a", "caso_b": "sha-b"}
    assert "evidencias_pre_pk_composta" not in tabelas2


def test_pk_composta_permite_mesmo_evidencia_id_em_casos_diferentes(tmp_path):
    """A raiz do bug: `evidencia_id` (ev_NNNNNN) e sequencial POR CASO -- 2
    casos diferentes podem gerar o MESMO id. Com a PK composta (caso_id, id)
    isso nao colide (a PK unica antiga silenciosamente descartava o segundo
    via INSERT OR IGNORE)."""
    db = DB(db_path=tmp_path / "casos.db")
    with db._lock, db.connect() as conn:
        conn.execute("INSERT INTO casos VALUES ('caso_a','A','livre','{}','[]',1,1)")
        conn.execute("INSERT INTO casos VALUES ('caso_b','B','livre','{}','[]',1,1)")
        conn.execute(
            "INSERT INTO evidencias (id, caso_id, tipo, caminho_local, url_origem, sha256, bytes, content_type, coletado_em) "
            "VALUES ('ev_000001','caso_a','pdf','a.pdf','https://x','sha-a',1,'application/pdf',1.0)"
        )
        conn.execute(
            "INSERT INTO evidencias (id, caso_id, tipo, caminho_local, url_origem, sha256, bytes, content_type, coletado_em) "
            "VALUES ('ev_000001','caso_b','pdf','b.pdf','https://x','sha-b',2,'application/pdf',2.0)"
        )
        conn.commit()
        rows = conn.execute("SELECT caso_id, sha256 FROM evidencias ORDER BY caso_id").fetchall()
    assert len(rows) == 2
    assert {r["caso_id"]: r["sha256"] for r in rows} == {"caso_a": "sha-a", "caso_b": "sha-b"}


def test_migracao_e_idempotente_reabrir_nao_falha_nem_duplica(tmp_path):
    db_path = tmp_path / "casos.db"
    db1 = DB(db_path=db_path)
    with db1._lock, db1.connect() as conn:
        conn.execute(
            "INSERT INTO casos (id, titulo, tipo, alvos_json, municipios_json, criado_em, atualizado_em) "
            "VALUES ('caso_x','X','livre','{}','[]',1,1)"
        )
        conn.execute(
            "INSERT INTO evidencias (id, caso_id, tipo, caminho_local, url_origem, sha256, bytes, content_type, coletado_em) "
            "VALUES ('ev_000001','caso_x','pdf','a.pdf','https://x','sha',1,'application/pdf',1.0)"
        )
        conn.commit()

    db2 = DB(db_path=db_path)  # reabre -- ja esta na PK composta, migracao e no-op
    with db2._lock, db2.connect() as conn:
        total = conn.execute("SELECT COUNT(*) AS n FROM evidencias").fetchone()["n"]
    assert total == 1
