"""Registry de secoes implementadas."""

from .base import Section
from .contratos import Contratos
from .despesas import Despesas
from .licitacoes import Licitacoes

SECTIONS: dict[str, type[Section]] = {
    "contratos": Contratos,
    "despesas": Despesas,
    "licitacoes": Licitacoes,
}

__all__ = ["Section", "SECTIONS", "Licitacoes", "Contratos", "Despesas"]
