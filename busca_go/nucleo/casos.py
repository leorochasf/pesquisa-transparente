"""Repositorio do caso/dossie (blueprint P2, doc AUDITORIA/refatoracao/04-blueprint.md
§4-§5). Cria/lista/agrega itens/anota casos e controla o ciclo de vida das
buscas (jobs) que rodam em background via asyncio (ver `busca_go/api.py`).

Toda funcao aceita `db: DB | None` (injetavel em teste); por padrao usa
`db.default_db()` (singleton em `data/casos.db`).
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
import uuid
from typing import Any

from ..db import DB, default_db

# Status possiveis de uma busca (job): fila -> rodando -> concluida|erro.
# 'interrompida' e exclusivo de recuperacao no boot (processo morreu no meio).
STATUS_TERMINAIS = {"concluida", "erro", "interrompida"}


def _slugify(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in nfkd if not unicodedata.combining(c))
    slug = re.sub(r"[^a-z0-9]+", "-", sem_acento.lower()).strip("-")
    return slug or "caso"


# ---------- casos ----------


def criar_caso(
    titulo: str,
    tipo: str,
    alvos: dict[str, Any],
    municipios: list[str],
    db: DB | None = None,
) -> dict[str, Any]:
    banco = db or default_db()
    agora = time.time()
    data_str = time.strftime("%Y%m%d", time.localtime(agora))
    sufixo = uuid.uuid4().hex[:6]
    caso_id = f"caso_{_slugify(titulo)}_{data_str}_{sufixo}"
    with banco._lock, banco.connect() as conn:
        conn.execute(
            """INSERT INTO casos
               (id, titulo, tipo, alvos_json, municipios_json, criado_em, atualizado_em)
               VALUES (?,?,?,?,?,?,?)""",
            (
                caso_id,
                titulo,
                tipo,
                json.dumps(alvos, ensure_ascii=False),
                json.dumps(municipios, ensure_ascii=False),
                agora,
                agora,
            ),
        )
        conn.commit()
    caso = obter_caso(caso_id, db=banco)
    assert caso is not None
    return caso


def listar_casos(db: DB | None = None) -> list[dict[str, Any]]:
    banco = db or default_db()
    with banco._lock, banco.connect() as conn:
        rows = conn.execute(
            "SELECT id, titulo, tipo, alvos_json, municipios_json, criado_em, atualizado_em "
            "FROM casos ORDER BY criado_em DESC"
        ).fetchall()
    return [
        {
            "id": r["id"],
            "titulo": r["titulo"],
            "tipo": r["tipo"],
            "alvos": json.loads(r["alvos_json"]),
            "municipios": json.loads(r["municipios_json"]),
            "criado_em": r["criado_em"],
            "atualizado_em": r["atualizado_em"],
        }
        for r in rows
    ]


def obter_caso(caso_id: str, db: DB | None = None) -> dict[str, Any] | None:
    banco = db or default_db()
    with banco._lock, banco.connect() as conn:
        row = conn.execute("SELECT * FROM casos WHERE id = ?", (caso_id,)).fetchone()
        if row is None:
            return None
        itens = conn.execute(
            "SELECT * FROM itens WHERE caso_id = ? ORDER BY criado_em", (caso_id,)
        ).fetchall()
        evidencias = conn.execute(
            "SELECT * FROM evidencias WHERE caso_id = ? ORDER BY coletado_em", (caso_id,)
        ).fetchall()
        anotacoes = conn.execute(
            "SELECT * FROM anotacoes WHERE caso_id = ? ORDER BY criado_em", (caso_id,)
        ).fetchall()
    return {
        "id": row["id"],
        "titulo": row["titulo"],
        "tipo": row["tipo"],
        "alvos": json.loads(row["alvos_json"]),
        "municipios": json.loads(row["municipios_json"]),
        "criado_em": row["criado_em"],
        "atualizado_em": row["atualizado_em"],
        "itens": [_item_row_to_dict(r) for r in itens],
        "evidencias": [_evidencia_row_to_dict(r) for r in evidencias],
        "anotacoes": [_anotacao_row_to_dict(r) for r in anotacoes],
    }


def _tocar_caso(caso_id: str, db: DB) -> None:
    with db._lock, db.connect() as conn:
        conn.execute("UPDATE casos SET atualizado_em = ? WHERE id = ?", (time.time(), caso_id))
        conn.commit()


# ---------- itens ----------


def _item_row_to_dict(r: Any) -> dict[str, Any]:
    return {
        "id": r["id"],
        "caso_id": r["caso_id"],
        "municipio": r["municipio"],
        "secao": r["secao"],
        "titulo": r["titulo"],
        "documento": r["documento"],
        "valor": r["valor"],
        "data": r["data"],
        "ref_registro": json.loads(r["ref_registro_json"]) if r["ref_registro_json"] else None,
        "raw": json.loads(r["raw_json"]),
        "origem": json.loads(r["origem_json"]) if r["origem_json"] else None,
        "criado_em": r["criado_em"],
    }


def _chave_dedup(item: dict[str, Any]) -> str | None:
    """Chave estavel do registro para nao duplicar o mesmo achado (blueprint §3.2):
    `ref_registro.id` do portal (contratos/dispensas/licitacoes) ou
    matricula+periodo (folha, identificador natural do servidor no mes).

    Sem nenhum dos dois, retorna None -- NAO deduplica (review R2, F-04):
    o fallback (numero,data,valor) do blueprint pode colidir por coincidencia
    entre dois achados genuinamente distintos (ex.: mesma descricao generica,
    mesma data, mesmo valor redondo); como o dossie e prova, colapsar dois
    registros diferentes numa linha so (raw_json do primeiro sobrescrito) e
    pior do que persistir os dois separados."""
    ref = item.get("ref_registro")
    rid = ref.get("id") if isinstance(ref, dict) else None
    if rid:
        return f"id:{rid}"
    if item.get("matricula"):
        return f"folha:{item.get('matricula')}:{item.get('ano')}:{item.get('mes')}"
    return None


def _item_id(caso_id: str, municipio: str, secao: str, item: dict[str, Any]) -> str:
    chave = _chave_dedup(item)
    if chave is None:
        # Sem identificador estavel do portal: cada insercao vira uma linha
        # nova (nunca colapsa com outra) -- ver `_chave_dedup`.
        chave = f"sem-id:{uuid.uuid4().hex}"
    raw = f"{caso_id}:{municipio}:{secao}:{chave}".encode("utf-8")
    return "it_" + hashlib.sha256(raw).hexdigest()[:20]


def adicionar_item(
    caso_id: str,
    municipio: str,
    secao: str,
    item: dict[str, Any],
    origem: list[str] | None = None,
    db: DB | None = None,
) -> str:
    """Insere (ou atualiza, se a chave de dedup ja existir) um item do caso.
    Mesmo achado encontrado de novo (reexecucao) nao vira linha duplicada."""
    banco = db or default_db()
    item_id = _item_id(caso_id, municipio, secao, item)
    ref_registro = item.get("ref_registro")
    with banco._lock, banco.connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO itens
               (id, caso_id, municipio, secao, titulo, documento, valor, data,
                ref_registro_json, raw_json, origem_json, criado_em)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                item_id,
                caso_id,
                municipio,
                secao,
                item.get("titulo") or item.get("nome"),
                item.get("documento") or item.get("matricula"),
                item.get("valor") or item.get("liquido"),
                item.get("data") or (f"{item.get('ano')}-{item.get('mes')}" if item.get("ano") else None),
                json.dumps(ref_registro, ensure_ascii=False) if ref_registro else None,
                json.dumps(item, ensure_ascii=False),
                json.dumps(origem, ensure_ascii=False) if origem else None,
                time.time(),
            ),
        )
        conn.commit()
    return item_id


def obter_item(item_id: str, db: DB | None = None) -> dict[str, Any] | None:
    banco = db or default_db()
    with banco._lock, banco.connect() as conn:
        row = conn.execute("SELECT * FROM itens WHERE id = ?", (item_id,)).fetchone()
    return _item_row_to_dict(row) if row is not None else None


def adicionar_itens_da_busca(
    caso_id: str,
    municipio: str,
    secao: str,
    itens: list[dict[str, Any]],
    origem: list[str] | None = None,
    db: DB | None = None,
) -> int:
    """Ponto de encaixe do job de busca: recebe os `itens` ja normalizados de
    um grupo de `entidade.pesquisar` e persiste no caso. Retorna quantos itens
    foram processados nesta chamada (dedup acontece por chave, nao aqui)."""
    banco = db or default_db()
    for item in itens:
        adicionar_item(caso_id, municipio, secao, item, origem=origem, db=banco)
    if itens:
        _tocar_caso(caso_id, banco)
    return len(itens)


# ---------- evidencias ----------


def _evidencia_row_to_dict(r: Any) -> dict[str, Any]:
    return {
        "id": r["id"],
        "caso_id": r["caso_id"],
        "item_id": r["item_id"],
        "tipo": r["tipo"],
        "caminho_local": r["caminho_local"],
        "url_origem": r["url_origem"],
        "sha256": r["sha256"],
        "bytes": r["bytes"],
        "content_type": r["content_type"],
        "coletado_em": r["coletado_em"],
    }


# ---------- anotacoes ----------


def _anotacao_row_to_dict(r: Any) -> dict[str, Any]:
    return {
        "id": r["id"],
        "caso_id": r["caso_id"],
        "item_id": r["item_id"],
        "tag": r["tag"],
        "texto": r["texto"],
        "criado_em": r["criado_em"],
    }


def adicionar_anotacao(
    caso_id: str,
    item_id: str | None,
    tag: str | None,
    texto: str,
    db: DB | None = None,
) -> dict[str, Any]:
    banco = db or default_db()
    anotacao_id = "an_" + uuid.uuid4().hex[:16]
    agora = time.time()
    with banco._lock, banco.connect() as conn:
        conn.execute(
            "INSERT INTO anotacoes (id, caso_id, item_id, tag, texto, criado_em) VALUES (?,?,?,?,?,?)",
            (anotacao_id, caso_id, item_id, tag, texto, agora),
        )
        conn.commit()
    _tocar_caso(caso_id, banco)
    return {
        "id": anotacao_id,
        "caso_id": caso_id,
        "item_id": item_id,
        "tag": tag,
        "texto": texto,
        "criado_em": agora,
    }


# ---------- buscas (jobs) ----------


def criar_busca(caso_id: str, parametros: dict[str, Any], db: DB | None = None) -> str:
    banco = db or default_db()
    job_id = "job_" + uuid.uuid4().hex[:16]
    agora = time.time()
    with banco._lock, banco.connect() as conn:
        conn.execute(
            """INSERT INTO buscas
               (id, caso_id, parametros_json, resultado_resumo_json, status,
                progresso_json, iniciada_em, concluida_em)
               VALUES (?,?,?,NULL,'fila',NULL,?,NULL)""",
            (job_id, caso_id, json.dumps(parametros, ensure_ascii=False), agora),
        )
        conn.commit()
    return job_id


def marcar_busca_status(
    job_id: str,
    status: str,
    progresso: dict[str, Any] | None = None,
    resultado_resumo: dict[str, Any] | None = None,
    db: DB | None = None,
) -> None:
    banco = db or default_db()
    campos = ["status = ?"]
    valores: list[Any] = [status]
    if progresso is not None:
        campos.append("progresso_json = ?")
        valores.append(json.dumps(progresso, ensure_ascii=False))
    if resultado_resumo is not None:
        campos.append("resultado_resumo_json = ?")
        valores.append(json.dumps(resultado_resumo, ensure_ascii=False))
    if status in STATUS_TERMINAIS:
        campos.append("concluida_em = ?")
        valores.append(time.time())
    valores.append(job_id)
    with banco._lock, banco.connect() as conn:
        conn.execute(f"UPDATE buscas SET {', '.join(campos)} WHERE id = ?", valores)
        conn.commit()


def obter_busca(job_id: str, db: DB | None = None) -> dict[str, Any] | None:
    banco = db or default_db()
    with banco._lock, banco.connect() as conn:
        row = conn.execute("SELECT * FROM buscas WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "caso_id": row["caso_id"],
        "parametros": json.loads(row["parametros_json"]),
        "resultado_resumo": json.loads(row["resultado_resumo_json"]) if row["resultado_resumo_json"] else None,
        "status": row["status"],
        "progresso": json.loads(row["progresso_json"]) if row["progresso_json"] else None,
        "iniciada_em": row["iniciada_em"],
        "concluida_em": row["concluida_em"],
    }


def recuperar_jobs_interrompidos(db: DB | None = None) -> int:
    """Chamado no boot do servidor (lifespan): jobs presos em 'fila'/'rodando'
    pertencem a um processo anterior que morreu -- a asyncio task ja nao
    existe, entao nunca ficam 'rodando' fantasma. Retorna quantos foram
    marcados."""
    banco = db or default_db()
    agora = time.time()
    with banco._lock, banco.connect() as conn:
        cur = conn.execute(
            "UPDATE buscas SET status = 'interrompida', concluida_em = ? "
            "WHERE status IN ('fila','rodando')",
            (agora,),
        )
        conn.commit()
    return cur.rowcount


__all__ = [
    "criar_caso",
    "listar_casos",
    "obter_caso",
    "adicionar_item",
    "obter_item",
    "adicionar_itens_da_busca",
    "adicionar_anotacao",
    "criar_busca",
    "marcar_busca_status",
    "obter_busca",
    "recuperar_jobs_interrompidos",
]
