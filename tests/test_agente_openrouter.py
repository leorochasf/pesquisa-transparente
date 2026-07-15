"""Testes do cliente OpenRouter: retry, contagem de tokens/custo, erros.

Sem rede: httpx.MockTransport reproduz o formato OpenAI-compativel de chat
completions com function-calling (blueprint AUDITORIA/refatoracao/04-blueprint.md §6.1).
"""

from __future__ import annotations

import json

import httpx
import pytest

from busca_go.agente import openrouter as openrouter_module
from busca_go.agente.openrouter import CustoAcumulado, OpenRouterClient, OpenRouterError


def _client(transport: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=transport, base_url="https://x")


async def test_chat_devolve_message_e_registra_usage():
    def handler(request: httpx.Request) -> httpx.Response:
        corpo = json.loads(request.content.decode())
        assert corpo["model"] == "deepseek/deepseek-v4-flash"
        assert corpo["usage"] == {"include": True}
        assert request.headers["authorization"] == "Bearer chave-teste"
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "ola"}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20, "cost": 0.0012},
            },
        )

    custo = CustoAcumulado()
    async with _client(httpx.MockTransport(handler)) as http_cli:
        cliente = OpenRouterClient("chave-teste", "https://x", custo, client=http_cli)
        msg = await cliente.chat("deepseek/deepseek-v4-flash", [{"role": "user", "content": "oi"}])

    assert msg["content"] == "ola"
    assert custo.tokens_prompt == 100
    assert custo.tokens_completion == 20
    assert custo.tokens_total == 120
    assert custo.custo_usd == pytest.approx(0.0012)
    assert custo.chamadas == 1


async def test_chat_acumula_custo_entre_varias_chamadas():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "x"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.0001},
            },
        )

    custo = CustoAcumulado()
    async with _client(httpx.MockTransport(handler)) as http_cli:
        cliente = OpenRouterClient("k", "https://x", custo, client=http_cli)
        await cliente.chat("modelo-a", [{"role": "user", "content": "1"}])
        await cliente.chat("modelo-b", [{"role": "user", "content": "2"}])

    assert custo.tokens_total == 30
    assert custo.custo_usd == pytest.approx(0.0002)
    assert custo.chamadas == 2


async def test_chat_envia_tools_e_tool_choice():
    capturado = {}

    def handler(request: httpx.Request) -> httpx.Response:
        capturado["corpo"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": []}}]})

    tools = [{"type": "function", "function": {"name": "minha_tool", "parameters": {}}}]
    async with _client(httpx.MockTransport(handler)) as http_cli:
        cliente = OpenRouterClient("k", "https://x", CustoAcumulado(), client=http_cli)
        await cliente.chat(
            "modelo",
            [{"role": "user", "content": "oi"}],
            tools=tools,
            tool_choice={"type": "function", "function": {"name": "minha_tool"}},
        )

    assert capturado["corpo"]["tools"] == tools
    assert capturado["corpo"]["tool_choice"] == {"type": "function", "function": {"name": "minha_tool"}}


async def test_status_diferente_de_200_vira_openroutererror():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="invalid api key")

    async with _client(httpx.MockTransport(handler)) as http_cli:
        cliente = OpenRouterClient("k", "https://x", CustoAcumulado(), client=http_cli)
        with pytest.raises(OpenRouterError):
            await cliente.chat("modelo", [{"role": "user", "content": "oi"}])


async def test_sem_choices_vira_openroutererror():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"erro": "algo deu errado"})

    async with _client(httpx.MockTransport(handler)) as http_cli:
        cliente = OpenRouterClient("k", "https://x", CustoAcumulado(), client=http_cli)
        with pytest.raises(OpenRouterError):
            await cliente.chat("modelo", [{"role": "user", "content": "oi"}])


async def test_corpo_nao_json_vira_openroutererror():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="nao e json")

    async with _client(httpx.MockTransport(handler)) as http_cli:
        cliente = OpenRouterClient("k", "https://x", CustoAcumulado(), client=http_cli)
        with pytest.raises(OpenRouterError):
            await cliente.chat("modelo", [{"role": "user", "content": "oi"}])


async def test_falha_de_rede_persistente_vira_openroutererror(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(openrouter_module, "_BACKOFF_SEGUNDOS", 0.0)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("conexao recusada", request=request)

    async with _client(httpx.MockTransport(handler)) as http_cli:
        cliente = OpenRouterClient("k", "https://x", CustoAcumulado(), client=http_cli, timeout_s=1.0)
        with pytest.raises(OpenRouterError):
            await cliente.chat("modelo", [{"role": "user", "content": "oi"}])


async def test_usage_ausente_nao_quebra_registrar():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]})

    custo = CustoAcumulado()
    async with _client(httpx.MockTransport(handler)) as http_cli:
        cliente = OpenRouterClient("k", "https://x", custo, client=http_cli)
        await cliente.chat("modelo", [{"role": "user", "content": "oi"}])

    assert custo.tokens_total == 0
    assert custo.custo_usd is None
    assert custo.chamadas == 1
