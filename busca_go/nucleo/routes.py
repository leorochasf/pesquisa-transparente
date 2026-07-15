"""Tabela de rotas explicita: (municipio, secao) -> path(s) reais NucleoGov.

A descoberta ao vivo (2026-07-07, `AUDITORIA/rotas/*.md`) provou que NAO existe
um template unico de path que sirva a todos os portais: cada municipio tem
rotas proprias, e ate dentro do mesmo municipio o prefixo varia por secao
(`cidadao/informacao/...`, `cidadao/transparencia/cnt...`, `cidadao/legislacao/...`,
`_frl`, `_psc`, legado `/informacao/...` sem `cidadao/`, e ate rota por id
`mp/id=1`). Por isso o roteamento e uma TABELA ESTATICA, path a path, e nunca
um pattern deduzido.

Estrutura:
- SECOES: catalogo canonico das secoes (10). `aditamentos` esta no catalogo mas
  e PER-MUNICIPIO — so tem rota onde o portal expoe pagina propria (ver nota).
- ROTAS:  dict municipio -> secao -> lista de paths (relativos ao host, sem
  barra inicial). A lista permite que UMA secao mape para MAIS DE UMA pagina
  (ex.: `legislacao` = leis + decretos + portarias); o fetch busca cada uma e
  concatena os itens. Uma (municipio, secao) so aparece aqui se a descoberta
  ao vivo confirmou rota COM DADOS.
- resolve(municipio, secao, query): monta a(s) URL(s) final(is) (lista).
- secoes_disponiveis(slug): secoes que aquele municipio realmente expoe.

REGRA ANTI-ALUCINACAO: todo path abaixo foi aberto e confirmado ao vivo nos
relatorios de `AUDITORIA/rotas/`. Nao adicione/edite um path sem uma fonte que
o confirme.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from ..municipios import Municipio


# 10 secoes canonicas (ordem alfabetica para consistencia de UI).
#
# `aditamentos` e PER-MUNICIPIO: em alguns portais (Cristalina, Itumbiara, Sao
# Miguel do Araguaia) e uma secao propria, com rota-lista dedicada (slug real
# `aditivos`, ex.: `informacao/aditivos_cnt`); em outros (Rio Verde, Senador
# Canedo, Trindade) NAO tem pagina propria — aparece so como linhas dentro da
# tabela de `contratos` (subconjunto/filtro). Por isso `aditamentos` esta no
# catalogo canonico, mas so aparece em ROTAS para os municipios que expoem a
# rota real; `secoes_disponiveis(slug)` cuida de nao oferecer onde nao existe.
SECOES: list[str] = [
    "aditamentos",
    "atas",
    "contratos",
    "despesas",
    "dispensas",
    "folha",
    "legislacao",
    "licitacoes",
    "receitas",
    "sancoes",
]


# Tabela de rotas reais por municipio. Cada valor e uma LISTA de paths (uma
# secao pode ter varias sub-paginas). Fonte: AUDITORIA/rotas/<slug>.md.
ROTAS: dict[str, dict[str, list[str]]] = {
    # --- Rio Verde (AUDITORIA/rotas/rioverde.md) ---
    # Prefixo obrigatorio /cidadao/<categoria>/<slug>; categoria varia por secao.
    "rioverde": {
        "legislacao": ["cidadao/legislacao/leis"],
        "receitas": ["cidadao/transparencia/cntreceitas"],
        "despesas": ["cidadao/transparencia/cntdespesas"],
        "folha": ["cidadao/transparencia/servidores_cnt"],
        "licitacoes": ["cidadao/informacao/licitacoes"],
        "dispensas": ["cidadao/informacao/dispensas"],
        "contratos": ["cidadao/informacao/contratos"],
        "atas": ["cidadao/informacao/atasregistropreco"],
        # sancoes servida por rota generica por id (nao por slug); id=1 e
        # especifico deste municipio.
        "sancoes": ["cidadao/informacao/mp/id=1"],
    },
    # --- Senador Canedo (AUDITORIA/rotas/senadorcanedo.md) ---
    # Convivem 3 convencoes: sufixo `_frl`, sufixo `_psc` (legislacao) e nomes
    # completos sem sufixo (sancoes). `atas` nao existe como rota propria aqui.
    "senadorcanedo": {
        "licitacoes": ["cidadao/informacao/licitacoes_frl"],
        "dispensas": ["cidadao/informacao/dispensas_frl"],
        "contratos": ["cidadao/informacao/contratos_frl"],
        "receitas": ["cidadao/transparencia/receitas_frl"],
        "despesas": ["cidadao/transparencia/despesas_frl"],
        # slug real de folha e "servidores", nao "folha".
        "folha": ["cidadao/transparencia/servidores_frl"],
        "sancoes": ["cidadao/informacao/sancoes_administrativas"],
        # legislacao = 2 sub-paginas (sufixo _psc), concatenadas.
        "legislacao": [
            "cidadao/legislacao/portarias_psc",
            "cidadao/legislacao/decretos_psc",
        ],
    },
    # --- Trindade (AUDITORIA/rotas/trindade.md) ---
    # Mistura /cidadao/informacao/<slug>, /cidadao/transparencia/cnt<slug>,
    # /cidadao/legislacao/<tipo> e paths legados /informacao/<slug> (sem
    # `cidadao/`) para contratos e licitacoes. WAF barra UA HeadlessChrome (403).
    "trindade": {
        "atas": ["cidadao/informacao/atasregistropreco"],
        # contratos e licitacoes: rota legada servida direto, sem `cidadao/`.
        "contratos": ["informacao/contratos"],
        "licitacoes": ["informacao/licitacoes"],
        "despesas": ["cidadao/transparencia/cntdespesas"],
        "dispensas": ["cidadao/informacao/dispensas"],
        "folha": ["cidadao/transparencia/servidores_cnt"],
        "receitas": ["cidadao/transparencia/cntreceitas"],
        "sancoes": ["cidadao/informacao/sancoes_administrativas"],
        # legislacao = 3 sub-paginas, concatenadas.
        "legislacao": [
            "cidadao/legislacao/leis",
            "cidadao/legislacao/decretos",
            "cidadao/legislacao/portarias",
        ],
    },
    # --- Cristalina (AUDITORIA/rotas/cristalina.md) ---
    # `_cnt` como sufixo em informacao/*, mas `cnt` vira PREFIXO em
    # transparencia/cnt<slug>. folha usa slug `servidores`. legislacao sem
    # sufixo. `atas` nao existe como rota propria. `aditamentos` TEM rota
    # propria aqui (aba "Aditivos e Distratos"): `aditivos_cnt`.
    "cristalina": {
        "licitacoes": ["cidadao/informacao/licitacoes_cnt"],
        "dispensas": ["cidadao/informacao/dispensas_cnt"],
        "contratos": ["cidadao/informacao/contratos_cnt"],
        "aditamentos": ["cidadao/informacao/aditivos_cnt"],
        # sancoes: rota real confirmada; pode listar 0 registros ("sem
        # sancoes no periodo"), o que e um vazio legitimo, nao rota quebrada.
        "sancoes": ["cidadao/informacao/sancoes_administrativas"],
        "despesas": ["cidadao/transparencia/cntdespesas"],
        "receitas": ["cidadao/transparencia/cntreceitas"],
        "folha": ["cidadao/transparencia/servidores_cnt"],
        # legislacao = 4 sub-paginas, concatenadas.
        "legislacao": [
            "cidadao/legislacao/leis",
            "cidadao/legislacao/decretos",
            "cidadao/legislacao/portarias",
            "cidadao/legislacao/resolucoes",
        ],
    },
    # --- Itumbiara (AUDITORIA/rotas/itumbiara.md) ---
    # `_cnt` sufixo em informacao/*; `cnt` prefixo em transparencia/*; folha e
    # `sgservidores` (sem `_cnt`). legislacao sem sufixo. `atas` sem rota
    # propria. `aditamentos` (slug real `aditivos`) TEM rota propria e listagem.
    "itumbiara": {
        "licitacoes": ["cidadao/informacao/licitacoes_cnt"],
        "dispensas": ["cidadao/informacao/dispensas_cnt"],
        "contratos": ["cidadao/informacao/contratos_cnt"],
        "aditamentos": ["cidadao/informacao/aditivos_cnt"],
        "sancoes": ["cidadao/informacao/sancoes_administrativas"],
        "receitas": ["cidadao/transparencia/cntreceitas"],
        "despesas": ["cidadao/transparencia/cntdespesas"],
        "folha": ["cidadao/transparencia/sgservidores"],
        # legislacao = 3 sub-paginas, concatenadas.
        "legislacao": [
            "cidadao/legislacao/portarias",
            "cidadao/legislacao/decretos",
            "cidadao/legislacao/resolucoes",
        ],
    },
    # --- Sao Miguel do Araguaia (AUDITORIA/rotas/saomigueldoaraguaia.md) ---
    # Mistura `_cnt` (informacao/*), prefixo `sg_` (atas =
    # `sg_atasregistropreco`), prefixo `cnt` (transparencia/*), e legislacao
    # com sufixo `_cnt`. `aditamentos` (slug `aditivos`) TEM rota propria.
    "saomigueldoaraguaia": {
        "atas": ["cidadao/informacao/sg_atasregistropreco"],
        "contratos": ["cidadao/informacao/contratos_cnt"],
        "dispensas": ["cidadao/informacao/dispensas_cnt"],
        "licitacoes": ["cidadao/informacao/licitacoes_cnt"],
        "aditamentos": ["cidadao/informacao/aditivos_cnt"],
        "sancoes": ["cidadao/informacao/sancoes_administrativas"],
        "despesas": ["cidadao/transparencia/cntdespesas"],
        "receitas": ["cidadao/transparencia/cntreceitas"],
        "folha": ["cidadao/transparencia/servidores_cnt"],
        # legislacao: SO as sub-paginas NucleoGov (portarias/decretos).
        # As LEIS vivem num CMS externo (saomigueldoaraguaia.go.gov.br/leis/,
        # WordPress, sem tabela HTML) — FORA DO ESCOPO deste scraper tabular.
        "legislacao": [
            "cidadao/legislacao/portarias_cnt",
            "cidadao/legislacao/decretos_cnt",
        ],
    },
    # --- Caldazinha (AUDITORIA/rotas/caldazinha.md) ---
    # Sabor distinto: sufixo `_mg` em informacao/* (nao `_frl`/`_cnt`). folha
    # NAO segue o padrao `<slug>/listar` das outras cidades: e servida por um
    # modulo `megasoft` a parte (ver nucleo/capacidades.py). So as 4 secoes
    # abaixo foram investigadas ao vivo (URLs fornecidas pelo dono); as demais
    # nao tem rota confirmada e ficam de fora da tabela.
    "caldazinha": {
        "contratos": ["cidadao/informacao/contratos_mg"],
        "licitacoes": ["cidadao/informacao/licitacoes_mg"],
        "dispensas": ["cidadao/informacao/dispensas_mg"],
        "folha": ["cidadao/transparencia/mgservidores"],
    },
}


class SecaoIndisponivel(LookupError):
    """A secao existe no catalogo, mas o municipio nao expoe rota real para ela.

    Ex.: `atas` em Senador Canedo — a descoberta ao vivo nao achou pagina-lista
    dedicada, entao nao ha path a servir (nao inventamos um).
    """


def secoes_disponiveis(slug: str) -> list[str]:
    """Secoes que `slug` realmente expoe, em ordem canonica (subconjunto de SECOES).

    Retorna [] se o municipio nao estiver na tabela.
    """
    rotas_mun = ROTAS.get(slug, {})
    return [s for s in SECOES if s in rotas_mun]


def _paths(slug: str, secao: str) -> list[str]:
    """Paths reais (relativos ao host) de (slug, secao).

    Raises:
        KeyError: secao fora do catalogo canonico.
        SecaoIndisponivel: secao valida, mas sem rota real para este municipio.
    """
    if secao not in SECOES:
        raise KeyError(f"Secao '{secao}' desconhecida. Disponiveis: {', '.join(SECOES)}")
    rotas_mun = ROTAS.get(slug, {})
    paths = rotas_mun.get(secao)
    if not paths:
        disp = ", ".join(secoes_disponiveis(slug)) or "(nenhuma)"
        raise SecaoIndisponivel(
            f"Secao '{secao}' nao esta disponivel no portal de '{slug}'. "
            f"Secoes disponiveis: {disp}."
        )
    return paths


def resolve(municipio: Municipio, secao: str, query: dict[str, Any] | None = None) -> list[str]:
    """Monta a(s) URL(s) final(is) para `municipio` + `secao`.

    Retorna sempre uma LISTA de URLs completas (1 elemento no caso comum; mais
    de um para secoes multi-pagina como `legislacao`). Query params, quando
    presentes, sao anexados a cada URL.

    Raises:
        KeyError: se secao nao estiver no catalogo canonico.
        SecaoIndisponivel: se o municipio nao tiver rota real para a secao.
    """
    paths = _paths(municipio.slug, secao)
    clean: dict[str, Any] = {}
    if query:
        clean = {k: v for k, v in query.items() if v not in (None, "", [])}
    urls: list[str] = []
    for path in paths:
        url = f"{municipio.url_base}/{path}"
        if clean:
            url = f"{url}?{urlencode(clean, doseq=True)}"
        urls.append(url)
    return urls


__all__ = ["SECOES", "ROTAS", "resolve", "secoes_disponiveis", "SecaoIndisponivel"]
