"""Cliente OpenRouter: chat completions OpenAI-compativel com function-calling
(blueprint `AUDITORIA/refatoracao/04-blueprint.md` §6.1). Fino sobre httpx (ja
e dependencia do projeto) -- sem SDK novo.

Contabiliza tokens/custo acumulados de UMA investigacao em `CustoAcumulado`,
compartilhado entre a cabeca e todos os workers dessa investigacao. O corpo
da requisicao pede `usage: {"include": true}` -- a OpenRouter, quando
disponivel, devolve `usage.cost` (USD) na propria resposta; o cliente SO
soma o que o provedor informou, nunca estima preco por tabela local (mesma
regra anti-invencao do projeto: dado sem fonte verificada nao entra em
relatorio nem em guardrail de custo).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_TENTATIVAS_RETRY = 3
_BACKOFF_SEGUNDOS = 1.0


class OpenRouterError(RuntimeError):
    """Falha ao chamar a API OpenRouter (rede, HTTP != 200, corpo inesperado)."""


@dataclass
class CustoAcumulado:
    """Tokens/custo agregados de UMA investigacao (cabeca + todos os workers).

    `custo_usd` fica `None` enquanto a OpenRouter nao devolver `usage.cost`
    numa resposta -- nunca e estimado a partir de tabela de preco local.
    """

    tokens_prompt: int = 0
    tokens_completion: int = 0
    custo_usd: float | None = None
    chamadas: int = 0

    @property
    def tokens_total(self) -> int:
        return self.tokens_prompt + self.tokens_completion

    def registrar(self, usage: dict[str, Any] | None) -> None:
        self.chamadas += 1
        if not usage:
            return
        self.tokens_prompt += int(usage.get("prompt_tokens") or 0)
        self.tokens_completion += int(usage.get("completion_tokens") or 0)
        custo = usage.get("cost")
        if custo is not None:
            self.custo_usd = (self.custo_usd or 0.0) + float(custo)


class OpenRouterClient:
    """1 chamada de chat completion por `chat()`. `client` httpx.AsyncClient
    injetavel (teste com transport mockado, sem rede real)."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        custo: CustoAcumulado,
        client: httpx.AsyncClient | None = None,
        timeout_s: float = 60.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.custo = custo
        self._client = client
        self._fechar = client is None
        self._timeout_s = timeout_s

    def _cli(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout_s)
        return self._client

    async def aclose(self) -> None:
        if self._fechar and self._client is not None:
            await self._client.aclose()

    async def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        """1 chamada de chat completion. Retorna a `message` do primeiro choice.

        Raises:
            OpenRouterError: falha de rede persistente, status != 200, ou
                corpo sem `choices` (resposta inesperada -- nunca finge
                sucesso vazio).
        """
        corpo: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "usage": {"include": True},
            "temperature": temperature,
        }
        if tools:
            corpo["tools"] = tools
        if tool_choice is not None:
            corpo["tool_choice"] = tool_choice
        cli = self._cli()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        resp = await self._post_com_retry(cli, headers, corpo)
        if resp.status_code != 200:
            raise OpenRouterError(f"OpenRouter respondeu {resp.status_code}: {resp.text[:500]}")
        try:
            dados = resp.json()
        except ValueError as exc:
            raise OpenRouterError(f"OpenRouter devolveu corpo nao-JSON: {exc}") from exc
        escolhas = dados.get("choices")
        if not escolhas:
            raise OpenRouterError(f"OpenRouter devolveu resposta sem 'choices': {dados}")
        self.custo.registrar(dados.get("usage"))
        return escolhas[0]["message"]

    async def _post_com_retry(
        self, cli: httpx.AsyncClient, headers: dict[str, str], corpo: dict[str, Any]
    ) -> httpx.Response:
        ultimo_exc: BaseException | None = None
        for tentativa in range(_TENTATIVAS_RETRY):
            try:
                return await cli.post(f"{self.base_url}/chat/completions", json=corpo, headers=headers)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                ultimo_exc = exc
                if tentativa < _TENTATIVAS_RETRY - 1:
                    await asyncio.sleep(_BACKOFF_SEGUNDOS * (tentativa + 1))
        raise OpenRouterError(f"Falha de rede ao chamar OpenRouter: {ultimo_exc}") from ultimo_exc


__all__ = ["OpenRouterClient", "OpenRouterError", "CustoAcumulado"]
