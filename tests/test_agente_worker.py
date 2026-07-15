"""Testes do loop do worker (`busca_go/agente/worker.py`): guardrails §6.2
#1 (args invalidos viram tool_result de erro, worker corrige) e #2 (teto de
iteracoes -- aborta com resultado parcial, nunca trava). `OpenRouterClient`
mockado (sem rede): um stub que devolve mensagens roteirizadas."""

from __future__ import annotations

import json
from typing import Any

import pytest

from busca_go.agente import log as log_module
from busca_go.agente import tools
from busca_go.agente.openrouter import CustoAcumulado, OpenRouterError
from busca_go.agente.worker import executar_subtarefa
from busca_go.nucleo import evidencia

_SUBTAREFA = {"id": "st_001", "instrucao": "Busque contratos do CNPJ X em Trindade."}


@pytest.fixture(autouse=True)
def _isolar_log_dir(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Guardrail §6.2 #6 grava `agente-log.jsonl` em disco a cada tool-call --
    isola em tmp_path pra nao poluir `data/casos/` real durante os testes."""
    monkeypatch.setattr(evidencia.settings, "DATA_DIR", tmp_path)


class _ClienteRoteirizado:
    """Stub de `OpenRouterClient`: devolve as mensagens da lista `roteiro`,
    uma por chamada de `chat()` (nunca bate rede)."""

    def __init__(self, roteiro: list[dict[str, Any]]) -> None:
        self.roteiro = roteiro
        self.chamadas = 0
        self.custo = CustoAcumulado()

    async def chat(self, model, messages, tools=None, tool_choice=None, temperature=0.2):
        self.chamadas += 1
        if self.chamadas > len(self.roteiro):
            raise AssertionError("worker chamou o modelo mais vezes do que o roteiro previa")
        return self.roteiro[self.chamadas - 1]


def _tool_call(call_id: str, nome: str, args: dict[str, Any]) -> dict[str, Any]:
    return {"id": call_id, "function": {"name": nome, "arguments": json.dumps(args, ensure_ascii=False)}}


def _msg_com_tool_calls(*calls: dict[str, Any]) -> dict[str, Any]:
    return {"role": "assistant", "content": None, "tool_calls": list(calls)}


async def test_worker_finaliza_apos_tool_bem_sucedida(monkeypatch: pytest.MonkeyPatch):
    async def _fake_executar_tool(nome, args, *, caso_id, periodo=None):
        assert nome == "buscar_entidade"
        return {"grupos": [{"secao": "contratos", "itens": [{"item_id": "it_1"}]}], "avisos": []}

    monkeypatch.setattr("busca_go.agente.worker.executar_tool", _fake_executar_tool)

    roteiro = [
        _msg_com_tool_calls(_tool_call("c1", "buscar_entidade", {"slug": "trindade", "cnpj": "123"})),
        _msg_com_tool_calls(
            _tool_call(
                "c2",
                "finalizar_subtarefa",
                {"sucesso": True, "resumo": "1 contrato encontrado.", "item_ids": ["it_1"], "evidencia_ids": []},
            )
        ),
    ]
    cliente = _ClienteRoteirizado(roteiro)
    resultado = await executar_subtarefa(cliente, "deepseek/deepseek-v4-flash", _SUBTAREFA, "caso_x", max_iteracoes=8)

    assert resultado.sucesso is True
    assert resultado.resumo == "1 contrato encontrado."
    assert resultado.item_ids == ["it_1"]
    assert resultado.iteracoes == 2
    assert cliente.chamadas == 2


async def test_periodo_da_subtarefa_e_repassado_para_executar_tool(monkeypatch: pytest.MonkeyPatch):
    """F7: o worker propaga o `periodo` que a cabeca anexou na subtarefa para
    cada chamada de tool -- filtro deterministico, nao depende do worker LLM
    lembrar de aplicar o periodo sozinho."""
    periodos_recebidos = []

    async def _fake_executar_tool(nome, args, *, caso_id, periodo=None):
        periodos_recebidos.append(periodo)
        return {"grupos": [], "avisos": []}

    monkeypatch.setattr("busca_go.agente.worker.executar_tool", _fake_executar_tool)

    roteiro = [
        _msg_com_tool_calls(_tool_call("c1", "buscar_entidade", {"slug": "trindade", "nome": "X"})),
        _msg_com_tool_calls(_tool_call("c2", "finalizar_subtarefa", {"sucesso": True, "resumo": "ok"})),
    ]
    cliente = _ClienteRoteirizado(roteiro)
    subtarefa = {"id": "st_001", "instrucao": "Busque.", "periodo": [2024, 2025]}
    await executar_subtarefa(cliente, "modelo", subtarefa, "caso_x", max_iteracoes=8)

    assert periodos_recebidos == [(2024, 2025)]


async def test_subtarefa_sem_periodo_repassa_none(monkeypatch: pytest.MonkeyPatch):
    periodos_recebidos = []

    async def _fake_executar_tool(nome, args, *, caso_id, periodo=None):
        periodos_recebidos.append(periodo)
        return {"grupos": [], "avisos": []}

    monkeypatch.setattr("busca_go.agente.worker.executar_tool", _fake_executar_tool)

    roteiro = [
        _msg_com_tool_calls(_tool_call("c1", "buscar_entidade", {"slug": "trindade", "nome": "X"})),
        _msg_com_tool_calls(_tool_call("c2", "finalizar_subtarefa", {"sucesso": True, "resumo": "ok"})),
    ]
    cliente = _ClienteRoteirizado(roteiro)
    await executar_subtarefa(cliente, "modelo", _SUBTAREFA, "caso_x", max_iteracoes=8)

    assert periodos_recebidos == [None]


async def test_arg_invalido_vira_tool_result_de_erro_e_worker_continua(monkeypatch: pytest.MonkeyPatch):
    async def _fake_executar_tool(nome, args, *, caso_id, periodo=None):
        raise tools.ToolArgumentoInvalido("municipio invalido")

    monkeypatch.setattr("busca_go.agente.worker.executar_tool", _fake_executar_tool)

    roteiro = [
        _msg_com_tool_calls(_tool_call("c1", "buscar_entidade", {"slug": "marte"})),
        _msg_com_tool_calls(
            _tool_call("c2", "finalizar_subtarefa", {"sucesso": False, "resumo": "Municipio invalido informado."})
        ),
    ]
    cliente = _ClienteRoteirizado(roteiro)
    resultado = await executar_subtarefa(cliente, "modelo", _SUBTAREFA, "caso_x", max_iteracoes=8)

    assert resultado.sucesso is False
    assert resultado.resumo == "Municipio invalido informado."
    assert cliente.chamadas == 2  # o loop CONTINUOU apos o erro (nao abortou na hora)


async def test_teto_de_iteracoes_aborta_sem_travar(monkeypatch: pytest.MonkeyPatch):
    """Guardrail §6.2 #2: o modelo NUNCA chama finalizar_subtarefa -- o loop
    aborta no teto, nunca trava esperando."""

    async def _fake_executar_tool(nome, args, *, caso_id, periodo=None):
        return {"grupos": [], "avisos": []}

    monkeypatch.setattr("busca_go.agente.worker.executar_tool", _fake_executar_tool)

    roteiro = [_msg_com_tool_calls(_tool_call(f"c{i}", "buscar_entidade", {"slug": "trindade", "nome": "X"})) for i in range(10)]
    cliente = _ClienteRoteirizado(roteiro)
    resultado = await executar_subtarefa(cliente, "modelo", _SUBTAREFA, "caso_x", max_iteracoes=3)

    assert resultado.sucesso is False
    assert resultado.motivo_falha == "teto_iteracoes"
    assert resultado.iteracoes == 3
    assert cliente.chamadas == 3


async def test_sem_tool_call_devolve_resultado_parcial_sem_travar():
    roteiro = [{"role": "assistant", "content": "Nao sei o que fazer.", "tool_calls": []}]
    cliente = _ClienteRoteirizado(roteiro)
    resultado = await executar_subtarefa(cliente, "modelo", _SUBTAREFA, "caso_x", max_iteracoes=8)

    assert resultado.sucesso is False
    assert resultado.motivo_falha == "worker_sem_tool_call"
    assert resultado.resumo == "Nao sei o que fazer."
    assert cliente.chamadas == 1


async def test_falha_openrouter_devolve_resultado_falho_imediatamente():
    class _ClienteFalho:
        async def chat(self, *args, **kwargs):
            raise OpenRouterError("500 upstream")

    resultado = await executar_subtarefa(_ClienteFalho(), "modelo", _SUBTAREFA, "caso_x", max_iteracoes=8)
    assert resultado.sucesso is False
    assert "500 upstream" in (resultado.motivo_falha or "")
    assert resultado.iteracoes == 1


async def test_json_malformado_nos_argumentos_vira_tool_erro_sem_derrubar_loop():
    roteiro = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "c1", "function": {"name": "buscar_entidade", "arguments": "{nao e json"}}],
        },
        _msg_com_tool_calls(
            _tool_call("c2", "finalizar_subtarefa", {"sucesso": False, "resumo": "Argumentos invalidos, desisti."})
        ),
    ]
    cliente = _ClienteRoteirizado(roteiro)
    resultado = await executar_subtarefa(cliente, "modelo", _SUBTAREFA, "caso_x", max_iteracoes=8)
    assert resultado.sucesso is False
    assert resultado.resumo == "Argumentos invalidos, desisti."


# --------------------------------------------------------------------------- #
# Guardrail §6.2 #6 (review R4, F1): toda tool-call fica logada no dossie
# --------------------------------------------------------------------------- #


async def test_toda_tool_call_fica_logada_no_dossie(monkeypatch: pytest.MonkeyPatch):
    async def _fake_executar_tool(nome, args, *, caso_id, periodo=None):
        if nome == "buscar_entidade":
            return {"grupos": [{"secao": "contratos", "itens": [{"item_id": "it_1"}]}], "avisos": []}
        raise tools.ToolArgumentoInvalido("secao invalida")

    monkeypatch.setattr("busca_go.agente.worker.executar_tool", _fake_executar_tool)

    roteiro = [
        _msg_com_tool_calls(_tool_call("c1", "buscar_entidade", {"slug": "trindade", "cnpj": "123"})),
        _msg_com_tool_calls(_tool_call("c2", "baixar_evidencias_registro", {"slug": "trindade", "secao": "x"})),
        _msg_com_tool_calls(
            _tool_call("c3", "finalizar_subtarefa", {"sucesso": True, "resumo": "ok", "item_ids": ["it_1"]})
        ),
    ]
    cliente = _ClienteRoteirizado(roteiro)
    cliente.custo.registrar({"prompt_tokens": 100, "completion_tokens": 20, "cost": 0.001})
    await executar_subtarefa(cliente, "modelo", _SUBTAREFA, "caso_log_teste", max_iteracoes=8)

    entradas = log_module.ler_log("caso_log_teste")
    assert len(entradas) == 3
    assert [e["tool"] for e in entradas] == ["buscar_entidade", "baixar_evidencias_registro", "finalizar_subtarefa"]
    assert all(e["subtarefa_id"] == "st_001" for e in entradas)
    assert entradas[0]["is_error"] is False
    assert entradas[0]["argumentos"] == {"slug": "trindade", "cnpj": "123"}
    assert "contratos" in entradas[0]["resultado_resumo"]
    assert entradas[1]["is_error"] is True
    assert "secao invalida" in entradas[1]["resultado_resumo"]
    assert entradas[2]["is_error"] is False
    assert entradas[2]["resultado_resumo"] == "ok"
    for e in entradas:
        assert "timestamp" in e and e["timestamp"]
        assert e["tokens_total_acumulado"] >= 120  # ja inclui o registrado antes da 1a chamada real
    assert entradas[-1]["custo_usd_acumulado"] == pytest.approx(0.001)


async def test_json_malformado_tambem_fica_logado():
    roteiro = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "c1", "function": {"name": "buscar_entidade", "arguments": "{nao e json"}}],
        },
        _msg_com_tool_calls(_tool_call("c2", "finalizar_subtarefa", {"sucesso": False, "resumo": "desisti"})),
    ]
    cliente = _ClienteRoteirizado(roteiro)
    await executar_subtarefa(cliente, "modelo", _SUBTAREFA, "caso_log_json_malformado", max_iteracoes=8)

    entradas = log_module.ler_log("caso_log_json_malformado")
    assert len(entradas) == 2
    assert entradas[0]["tool"] == "buscar_entidade"
    assert entradas[0]["is_error"] is True
    assert "JSON malformado" in entradas[0]["resultado_resumo"]
