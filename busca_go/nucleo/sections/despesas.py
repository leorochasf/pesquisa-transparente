"""Secao: despesas."""

from __future__ import annotations

from .base import Section


class Despesas(Section):
    slug = "despesas"
    descricao = "Despesas empenhadas, liquidadas e pagas."
    filtros = {
        "ano": "Ano do empenho",
        "credor": "Nome ou CNPJ do credor",
    }


__all__ = ["Despesas"]
