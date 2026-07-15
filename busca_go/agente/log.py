"""Log estruturado de tool-calls do agente (guardrail §6.2 #6: "Toda tool-call
e logada... com tokens gastos — auditoria e reexecucao"). Grava, em
`data/casos/<id>/agente-log.jsonl` (append-only, mesmo padrao de
`nucleo/evidencia.py::registrar_evidencia`), UMA linha por tool-call real do
agente: timestamp, subtarefa, tool, argumentos, resultado resumido e o
tokens/custo ACUMULADO da investigacao naquele instante.

E o rastro de auditoria do que o robo fez -- requisito de produto de uma
ferramenta de prova, nao so acompanhamento tecnico: quem reabrir o caso
consegue reconstruir, passo a passo, toda decisao/tool-call do agente sem
depender do log de processo (que nao persiste no dossie).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..nucleo.evidencia import caminho_caso


def _agora_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log_path(caso_id: str) -> Path:
    return caminho_caso(caso_id) / "agente-log.jsonl"


def registrar_tool_call(
    caso_id: str,
    subtarefa_id: str,
    tool: str,
    argumentos: dict[str, Any],
    resultado_resumo: str,
    is_error: bool,
    tokens_total_acumulado: int,
    custo_usd_acumulado: float | None,
) -> None:
    """Grava UMA linha (append-only) com o rastro de UMA tool-call."""
    p = _log_path(caso_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    entrada = {
        "timestamp": _agora_iso(),
        "subtarefa_id": subtarefa_id,
        "tool": tool,
        "argumentos": argumentos,
        "resultado_resumo": resultado_resumo,
        "is_error": is_error,
        "tokens_total_acumulado": tokens_total_acumulado,
        "custo_usd_acumulado": custo_usd_acumulado,
    }
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entrada, ensure_ascii=False) + "\n")


def ler_log(caso_id: str) -> list[dict[str, Any]]:
    """Le todas as tool-calls logadas do caso (lista vazia se ainda nao existe)."""
    p = _log_path(caso_id)
    if not p.exists():
        return []
    linhas: list[dict[str, Any]] = []
    for linha in p.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha:
            linhas.append(json.loads(linha))
    return linhas


def resumo_resultado(resultado: dict[str, Any], limite: int = 500) -> str:
    """JSON compacto do resultado de uma tool, truncado -- log e resumo, nao
    reimpressao completa do payload (podem ser dezenas de itens/evidencias)."""
    texto = json.dumps(resultado, ensure_ascii=False)
    return texto if len(texto) <= limite else texto[:limite] + "…"


__all__ = ["registrar_tool_call", "ler_log", "resumo_resultado"]
