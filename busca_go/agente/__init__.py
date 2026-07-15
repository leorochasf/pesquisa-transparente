"""Agente investigador (OpenRouter, arquitetura cabeca/worker).

Camada de orquestracao sobre as funcoes internas de busca/download/evidencia
ja existentes (`nucleo/entidade.py`, `nucleo/centi.py`, `nucleo/evidencia.py`,
`nucleo/casos.py`) -- nunca uma via nova de dado (blueprint
`AUDITORIA/refatoracao/04-blueprint.md` §6). CABECA (`cabeca.py`, Gemini 3
Flash) planeja/despacha/valida/redige; WORKER (`worker.py`, DeepSeek V4 Flash)
roda o loop curto de tool-use de cada subtarefa (`tools.py`). Cliente OpenAI-
compativel fino sobre httpx em `openrouter.py`.
"""

from .cabeca import ResultadoInvestigacao, investigar

__all__ = ["investigar", "ResultadoInvestigacao"]
