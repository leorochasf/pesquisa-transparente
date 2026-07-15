"""Secao: contratos."""

from __future__ import annotations

from .base import Section


class Contratos(Section):
    slug = "contratos"
    descricao = "Contratos firmados pela prefeitura."
    filtros = {
        "cnpj": "CNPJ do contratado",
        "ano": "Ano de assinatura",
        "numero": "Numero do contrato",
    }


__all__ = ["Contratos"]
