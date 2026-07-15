"""Classe base para secoes de transparencia."""

from __future__ import annotations

from typing import Any

from ...municipios import Municipio
from ..routes import resolve


class Section:
    """Define contrato comum de uma secao: slug, descricao, filtros.

    Subclasses devem sobrescrever `slug`, `descricao` e `filtros`. O
    metodo `build_url` tem implementacao padrao que delega para
    `routes.resolve`; sobrescreva se a secao precisar de logica
    especial de URL. Retorna uma LISTA de URLs (uma secao pode ter mais
    de uma sub-pagina, ex.: legislacao).
    """

    slug: str = ""
    descricao: str = ""
    filtros: dict[str, str] = {}

    def build_url(self, municipio: Municipio, filtros: dict[str, Any] | None = None) -> list[str]:
        return resolve(municipio, self.slug, filtros or {})

    def validar_filtros(self, filtros: dict[str, Any]) -> dict[str, str]:
        """Retorna dict {campo: mensagem} de erros. Vazio = OK."""
        erros: dict[str, str] = {}
        if not self.slug:
            erros["__slug__"] = "Section.slug nao definido"
        for k in filtros:
            if k not in self.filtros:
                erros[k] = f"filtro '{k}' nao aceito por '{self.slug}' (aceitos: {sorted(self.filtros)})"
        return erros


__all__ = ["Section"]
