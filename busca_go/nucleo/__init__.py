"""Cliente e parsers para portais nucleogov."""

from .client import NavigationError, NucleoClient
from .parsers import ItemTransparencia, ParseError, parse_tabela_generica
from .routes import SECOES, SecaoIndisponivel, resolve, secoes_disponiveis

__all__ = [
    "NucleoClient",
    "NavigationError",
    "SecaoIndisponivel",
    "ItemTransparencia",
    "ParseError",
    "parse_tabela_generica",
    "SECOES",
    "resolve",
    "secoes_disponiveis",
]
