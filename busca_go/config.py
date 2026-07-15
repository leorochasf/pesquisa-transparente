"""Configuracao central via variaveis de ambiente."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Carrega `.env` da raiz do projeto (se existir) ANTES de qualquer os.getenv
# abaixo -- sem isso, um `.env` no disco nunca chegaria a `os.environ` (o
# processo so ve variaveis exportadas no shell). `.env` fica fora do git
# (.gitignore); chaves como OPENROUTER_API_KEY so existem nele.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _data_dir() -> Path:
    raw = os.getenv("BUSCA_GO_DATA_DIR", "./data")
    p = Path(raw).expanduser().resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


class Settings:
    DATA_DIR: Path = _data_dir()
    CACHE_DAYS: int = int(os.getenv("BUSCA_GO_CACHE_DAYS", "7"))
    TIMEOUT_MS: int = int(os.getenv("BUSCA_GO_TIMEOUT_MS", "30000"))
    HEADLESS: bool = os.getenv("BUSCA_GO_HEADLESS", "true").lower() in {"1", "true", "yes"}
    PORT: int = int(os.getenv("BUSCA_GO_PORT", "8000"))
    CORS_ORIGINS: list[str] = [
        o.strip()
        for o in os.getenv("BUSCA_GO_CORS_ORIGINS", "*").split(",")
        if o.strip()
    ]
    # Assina o token opaco de anexo (ver busca_go/nucleo/anexos.py) para que o
    # cliente nao possa forjar `ref` com URL arbitraria (SSRF). Troque em producao.
    ANEXO_REF_SECRET: str = os.getenv("BUSCA_GO_ANEXO_REF_SECRET", "dev-anexo-ref-secret-troque-em-producao")

    # Agente investigador via OpenRouter -- arquitetura cabeca/worker (blueprint
    # AUDITORIA/refatoracao/04-blueprint.md §6.4). Model-ids SEMPRE daqui, nunca
    # hardcoded em agente/*.py. Chave None se nao configurada -- o endpoint
    # /api/casos/{id}/investigar recusa com 400 nesse caso (ver busca_go/api.py).
    OPENROUTER_API_KEY: str | None = os.getenv("OPENROUTER_API_KEY") or None
    OPENROUTER_BASE_URL: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    # "google/gemini-3-flash" (nome do blueprint) nao existe no catalogo atual
    # da OpenRouter -- confirmado ao vivo (GET /models) nesta sessao,
    # 2026-07-14: o id real e "google/gemini-3-flash-preview" (blueprint §6.4
    # ja previa essa checagem: "catalogo do OpenRouter muda").
    OPENROUTER_MODEL_CABECA: str = os.getenv("OPENROUTER_MODEL_CABECA", "google/gemini-3-flash-preview")
    OPENROUTER_MODEL_WORKER: str = os.getenv("OPENROUTER_MODEL_WORKER", "deepseek/deepseek-v4-flash")
    # Teto de decomposicao da cabeca (guardrail §6.2).
    AGENTE_MAX_SUBTAREFAS: int = int(os.getenv("AGENTE_MAX_SUBTAREFAS", "20"))
    # Teto de tool-calls por subtarefa do worker (guardrail §6.2 #2).
    AGENTE_MAX_ITER_WORKER: int = int(os.getenv("AGENTE_MAX_ITER_WORKER", "8"))
    # Orcamento agregado (cabeca + workers) por investigacao -- Decisao 3 do
    # dono (teto folgado + entrega parcial honesta, `05-decisoes-do-dono.md`).
    # Tokens e a metrica confiavel (a OpenRouter sempre devolve `usage`); custo
    # em USD real, quando o provedor informa (`usage.cost`), so entra no
    # relatorio como informativo -- nunca e estimado por tabela de preco local.
    AGENTE_TETO_TOKENS: int = int(os.getenv("AGENTE_TETO_TOKENS", "1000000"))
    # 1800s (30min): a investigacao piloto real desta missao (Senador Canedo,
    # FL CONSTRUTORA, 142 evidencias baixadas) levou ~957s de ponta a ponta --
    # um teto de 900s (default anterior) ja teria sido atingido. 1800s mantem
    # "folgado" (Decisao 3) para casos com bastante PDF pra baixar, sem abrir
    # mao do teto como rede de seguranca.
    AGENTE_TETO_TEMPO_S: int = int(os.getenv("AGENTE_TETO_TEMPO_S", "1800"))

    @property
    def CACHE_DB(self) -> Path:
        return self.DATA_DIR / "busca_go.db"

    @property
    def CASOS_DB(self) -> Path:
        return self.DATA_DIR / "casos.db"


settings = Settings()