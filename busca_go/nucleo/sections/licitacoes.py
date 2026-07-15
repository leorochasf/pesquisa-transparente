"""Secao: licitacoes."""

from __future__ import annotations

from .base import Section


class Licitacoes(Section):
    slug = "licitacoes"
    descricao = "Editais, modalidades e resultados de licitacoes."
    filtros = {
        "ano": "Ano de referencia (ex.: 2025)",
        "modalidade": "Modalidade (pregao, tomada de precos, ...)",
        "cnpj": "CNPJ do licitante (com ou sem pontuacao)",
    }


__all__ = ["Licitacoes"]
