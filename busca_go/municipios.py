"""Registry de municipios goianos integrados ao portal nucleogov.

Cada entrada traz:
- slug:    subdominio (minusculas, sem acento, com hifens). Eixo do URL base.
- nome:    nome oficial para exibicao.
- plataforma: rotulo da plataforma do portal. Todos os municipios cobertos
              usam NucleoGov, mas o ROTEAMENTO real (path de cada secao) NAO
              deriva desse rotulo — ele varia por municipio e por secao, e
              esta mapeado path a path em `nucleo/routes.py` (ROTAS).
- url_base: derivado de slug. Apenas para consultas HTTP.

ESCOPO (decisao do dono, 2026-07-07; ampliado 2026-07-14 com Caldazinha): o
projeto cobre os 7 municipios abaixo, todos confirmados AO VIVO como NucleoGov
com rotas reais mapeadas em `nucleo/routes.py`. Goiania e Aparecida de Goiania
foram REMOVIDOS do projeto porque nao usam NucleoGov (sistemas externos) — ver
`AUDITORIA/rotas/goiania.md` e `AUDITORIA/rotas/aparecida.md` para o porque.

Caldazinha usa um SABOR distinto de NucleoGov (sufixo `_mg` em vez de `_frl`/
`_cnt`, e folha servida por um modulo `megasoft` a parte, com paginacao e
campos proprios) — ver `AUDITORIA/rotas/caldazinha.md` e
`nucleo/capacidades.py` (`modo_api="megasoft"`).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Municipio:
    slug: str
    nome: str
    plataforma: str = "nucleogov"

    @property
    def url_base(self) -> str:
        return f"https://acessoainformacao.{self.slug}.go.gov.br"


MUNICIPIOS: dict[str, Municipio] = {
    m.slug: m
    for m in [
        Municipio(slug="rioverde", nome="Rio Verde"),
        Municipio(slug="senadorcanedo", nome="Senador Canedo"),
        Municipio(slug="trindade", nome="Trindade"),
        Municipio(slug="cristalina", nome="Cristalina"),
        Municipio(slug="itumbiara", nome="Itumbiara"),
        Municipio(slug="saomigueldoaraguaia", nome="São Miguel do Araguaia"),
        Municipio(slug="caldazinha", nome="Caldazinha"),
    ]
}


def get(slug: str) -> Municipio:
    """Busca por slug. Levanta KeyError com mensagem clara se nao existir."""
    try:
        return MUNICIPIOS[slug]
    except KeyError as exc:
        disponiveis = ", ".join(sorted(MUNICIPIOS))
        raise KeyError(f"Municipio '{slug}' nao cadastrado. Disponiveis: {disponiveis}") from exc


def all_slugs() -> list[str]:
    return sorted(MUNICIPIOS)


__all__ = ["Municipio", "MUNICIPIOS", "get", "all_slugs"]
