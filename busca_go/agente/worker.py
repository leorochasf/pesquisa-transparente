"""Worker (DeepSeek V4 Flash): loop CURTO de tool-use por SUBTAREFA fechada
(blueprint `AUDITORIA/refatoracao/04-blueprint.md` §6.1, guardrails §6.2).

Cada subtarefa e UM (municipio, secao/identificador) -- o worker so ve o
enunciado dessa subtarefa (nunca o caso inteiro; isso e privilegio da
cabeca). O loop tem teto DURO de iteracoes (guardrail §2): estourou sem
`finalizar_subtarefa`, aborta com o resultado parcial e devolve a cabeca --
nunca trava, nunca inventa. Argumentos de tool invalidos viram `tool_result`
de erro para o proprio modelo corrigir na iteracao seguinte (guardrail #1).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from .log import registrar_tool_call, resumo_resultado
from .openrouter import OpenRouterClient, OpenRouterError
from .tools import TOOL_SCHEMAS_WORKER, ToolArgumentoInvalido, ToolExecucaoError, executar_tool

logger = logging.getLogger(__name__)


@dataclass
class ResultadoSubtarefa:
    """Resultado de UMA subtarefa -- estruturado, com as refs de evidencia que
    o worker afirma ter coletado (a cabeca confere contra o manifesto real
    antes de aceitar, ver `cabeca._validar_evidencias`)."""

    subtarefa_id: str
    sucesso: bool
    resumo: str
    item_ids: list[str] = field(default_factory=list)
    evidencia_ids: list[str] = field(default_factory=list)
    motivo_falha: str | None = None
    iteracoes: int = 0


_FINALIZAR_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "finalizar_subtarefa",
        "description": (
            "Encerra esta subtarefa e devolve o resultado estruturado. So chame "
            "depois de rodar as tools necessarias -- 'resumo' deve citar SO o que "
            "as tools devolveram (evidencia_ids/item_ids reais); nunca invente "
            "numero, valor ou data que nao veio de uma tool."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "sucesso": {"type": "boolean"},
                "resumo": {"type": "string", "description": "1-3 frases do que foi encontrado (ou por que falhou)."},
                "item_ids": {"type": "array", "items": {"type": "string"}},
                "evidencia_ids": {"type": "array", "items": {"type": "string"}},
                "motivo_falha": {"type": "string"},
            },
            "required": ["sucesso", "resumo"],
        },
    },
}

_SYSTEM_PROMPT = (
    "Voce e o WORKER de uma investigacao de transparencia publica. Recebeu UMA "
    "subtarefa fechada (1 municipio/secao/identificador). Use as tools "
    "disponiveis para coletar o resultado; NUNCA afirme um dado que nao veio "
    "de uma resposta de tool -- se as tools nao acharem nada, isso e um "
    "resultado legitimo (sucesso=true, resumo dizendo que nao ha registros). "
    "Quando terminar, chame 'finalizar_subtarefa'. Nao repita a mesma tool "
    "com os mesmos argumentos."
)


def _tool_ok(call_id: str, conteudo: dict[str, Any]) -> dict[str, Any]:
    return {"role": "tool", "tool_call_id": call_id, "content": json.dumps(conteudo, ensure_ascii=False)}


def _tool_erro(call_id: str, erro: str) -> dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": call_id,
        "content": json.dumps({"is_error": True, "erro": erro}, ensure_ascii=False),
    }


def _log(
    caso_id: str,
    subtarefa_id: str,
    tool: str,
    args: dict[str, Any],
    resumo: str,
    is_error: bool,
    cliente: OpenRouterClient,
) -> None:
    """Guardrail §6.2 #6: grava a tool-call no rastro de auditoria do dossie."""
    registrar_tool_call(
        caso_id, subtarefa_id, tool, args, resumo, is_error, cliente.custo.tokens_total, cliente.custo.custo_usd
    )


async def executar_subtarefa(
    cliente: OpenRouterClient,
    modelo: str,
    subtarefa: dict[str, Any],
    caso_id: str,
    max_iteracoes: int,
) -> ResultadoSubtarefa:
    """Loop curto de tool-use para UMA subtarefa (guardrails §6.2 #1 e #2)."""
    periodo_bruto = subtarefa.get("periodo")
    periodo: tuple[int, int] | None = tuple(periodo_bruto) if periodo_bruto else None  # type: ignore[assignment]
    mensagens: list[dict[str, Any]] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": subtarefa["instrucao"]},
    ]
    tools = [*TOOL_SCHEMAS_WORKER, _FINALIZAR_TOOL]
    iteracao = 0
    while iteracao < max_iteracoes:
        iteracao += 1
        try:
            msg = await cliente.chat(modelo, mensagens, tools=tools)
        except OpenRouterError as exc:
            return ResultadoSubtarefa(
                subtarefa_id=subtarefa["id"],
                sucesso=False,
                resumo="Falha ao chamar o worker (OpenRouter).",
                motivo_falha=str(exc),
                iteracoes=iteracao,
            )
        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            # Respondeu texto sem chamar finalizar_subtarefa -- nunca trava
            # esperando: devolve como resultado parcial nao estruturado.
            return ResultadoSubtarefa(
                subtarefa_id=subtarefa["id"],
                sucesso=False,
                resumo=(msg.get("content") or "").strip() or "Worker nao produziu resultado estruturado.",
                motivo_falha="worker_sem_tool_call",
                iteracoes=iteracao,
            )
        mensagens.append({"role": "assistant", "content": msg.get("content"), "tool_calls": tool_calls})
        finalizado: ResultadoSubtarefa | None = None
        for call in tool_calls:
            nome = call["function"]["name"]
            call_id = call["id"]
            try:
                args = json.loads(call["function"]["arguments"] or "{}")
            except json.JSONDecodeError as exc:
                erro = f"argumentos invalidos (JSON malformado): {exc}"
                mensagens.append(_tool_erro(call_id, erro))
                _log(caso_id, subtarefa["id"], nome, {}, erro, True, cliente)
                continue
            if nome == "finalizar_subtarefa":
                finalizado = ResultadoSubtarefa(
                    subtarefa_id=subtarefa["id"],
                    sucesso=bool(args.get("sucesso", True)),
                    resumo=str(args.get("resumo") or ""),
                    item_ids=[str(x) for x in (args.get("item_ids") or [])],
                    evidencia_ids=[str(x) for x in (args.get("evidencia_ids") or [])],
                    motivo_falha=args.get("motivo_falha"),
                    iteracoes=iteracao,
                )
                mensagens.append(_tool_ok(call_id, {"ok": True}))
                _log(caso_id, subtarefa["id"], nome, args, finalizado.resumo, False, cliente)
                continue
            try:
                resultado_tool = await executar_tool(nome, args, caso_id=caso_id, periodo=periodo)
                mensagens.append(_tool_ok(call_id, resultado_tool))
                _log(caso_id, subtarefa["id"], nome, args, resumo_resultado(resultado_tool), False, cliente)
            except ToolArgumentoInvalido as exc:
                mensagens.append(_tool_erro(call_id, str(exc)))
                _log(caso_id, subtarefa["id"], nome, args, str(exc), True, cliente)
            except ToolExecucaoError as exc:
                mensagens.append(_tool_erro(call_id, str(exc)))
                _log(caso_id, subtarefa["id"], nome, args, str(exc), True, cliente)
        if finalizado is not None:
            return finalizado
    # guardrail §6.2 #2: estourou o teto de iteracoes -- aborta com o que tiver.
    return ResultadoSubtarefa(
        subtarefa_id=subtarefa["id"],
        sucesso=False,
        resumo="Subtarefa abortada: excedeu o teto de iteracoes sem finalizar.",
        motivo_falha="teto_iteracoes",
        iteracoes=iteracao,
    )


__all__ = ["ResultadoSubtarefa", "executar_subtarefa"]
