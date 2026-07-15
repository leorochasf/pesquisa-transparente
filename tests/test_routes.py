"""Testes da tabela de rotas explicita (busca_go.nucleo.routes)."""

import pytest

from busca_go.municipios import Municipio, get as get_mun
from busca_go.nucleo.routes import (
    ROTAS,
    SECOES,
    SecaoIndisponivel,
    resolve,
    secoes_disponiveis,
)


def test_secoes_tem_10_entradas():
    # aditamentos voltou ao catalogo (per-municipio) -> 10 secoes.
    assert len(SECOES) == 10


def test_aditamentos_no_catalogo_mas_per_municipio():
    """aditamentos esta no catalogo canonico, mas so tem rota nos municipios que
    expoem pagina propria (Cristalina/Itumbiara/Sao Miguel). Os 3 primeiros
    (Rio Verde/Senador Canedo/Trindade) NAO tem a chave aditamentos."""
    assert "aditamentos" in SECOES
    # tem rota propria:
    for slug in ("cristalina", "itumbiara", "saomigueldoaraguaia"):
        assert "aditamentos" in ROTAS[slug], slug
    # nao tem rota propria (embutido em contratos):
    for slug in ("rioverde", "senadorcanedo", "trindade"):
        assert "aditamentos" not in ROTAS[slug], slug


def test_resolve_retorna_lista_de_urls():
    rv = get_mun("rioverde")
    urls = resolve(rv, "licitacoes")
    assert isinstance(urls, list)
    assert urls == ["https://acessoainformacao.rioverde.go.gov.br/cidadao/informacao/licitacoes"]


@pytest.mark.parametrize(
    "slug,secao,esperado",
    [
        # Rio Verde: prefixos variam por secao.
        ("rioverde", "legislacao", ["cidadao/legislacao/leis"]),
        ("rioverde", "receitas", ["cidadao/transparencia/cntreceitas"]),
        ("rioverde", "folha", ["cidadao/transparencia/servidores_cnt"]),
        ("rioverde", "atas", ["cidadao/informacao/atasregistropreco"]),
        ("rioverde", "sancoes", ["cidadao/informacao/mp/id=1"]),
        # Senador Canedo: sufixos _frl / nomes completos.
        ("senadorcanedo", "licitacoes", ["cidadao/informacao/licitacoes_frl"]),
        ("senadorcanedo", "folha", ["cidadao/transparencia/servidores_frl"]),
        ("senadorcanedo", "sancoes", ["cidadao/informacao/sancoes_administrativas"]),
        # Trindade: rotas legadas sem `cidadao/` para contratos/licitacoes.
        ("trindade", "contratos", ["informacao/contratos"]),
        ("trindade", "licitacoes", ["informacao/licitacoes"]),
        ("trindade", "despesas", ["cidadao/transparencia/cntdespesas"]),
        # Cristalina: `_cnt` sufixo vs `cnt` prefixo; folha = servidores_cnt.
        ("cristalina", "licitacoes", ["cidadao/informacao/licitacoes_cnt"]),
        ("cristalina", "despesas", ["cidadao/transparencia/cntdespesas"]),
        ("cristalina", "folha", ["cidadao/transparencia/servidores_cnt"]),
        ("cristalina", "aditamentos", ["cidadao/informacao/aditivos_cnt"]),
        # Itumbiara: folha e `sgservidores` (sem sufixo).
        ("itumbiara", "folha", ["cidadao/transparencia/sgservidores"]),
        ("itumbiara", "contratos", ["cidadao/informacao/contratos_cnt"]),
        ("itumbiara", "aditamentos", ["cidadao/informacao/aditivos_cnt"]),
        # Sao Miguel: atas com prefixo `sg_`.
        ("saomigueldoaraguaia", "atas", ["cidadao/informacao/sg_atasregistropreco"]),
        ("saomigueldoaraguaia", "licitacoes", ["cidadao/informacao/licitacoes_cnt"]),
        # Caldazinha: sufixo `_mg` (sabor distinto de `_frl`/`_cnt`).
        ("caldazinha", "contratos", ["cidadao/informacao/contratos_mg"]),
        ("caldazinha", "licitacoes", ["cidadao/informacao/licitacoes_mg"]),
        ("caldazinha", "dispensas", ["cidadao/informacao/dispensas_mg"]),
        ("caldazinha", "folha", ["cidadao/transparencia/mgservidores"]),
    ],
)
def test_resolve_path_esperado_por_municipio_e_secao(slug, secao, esperado):
    mun = get_mun(slug)
    urls = resolve(mun, secao)
    assert urls == [f"{mun.url_base}/{p}" for p in esperado]


def test_legislacao_multi_rota_trindade():
    """Trindade: legislacao mapeia para 3 sub-paginas (leis/decretos/portarias)."""
    t = get_mun("trindade")
    urls = resolve(t, "legislacao")
    assert urls == [
        "https://acessoainformacao.trindade.go.gov.br/cidadao/legislacao/leis",
        "https://acessoainformacao.trindade.go.gov.br/cidadao/legislacao/decretos",
        "https://acessoainformacao.trindade.go.gov.br/cidadao/legislacao/portarias",
    ]


def test_legislacao_multi_rota_senadorcanedo():
    """Senador Canedo: legislacao = portarias_psc + decretos_psc."""
    sc = get_mun("senadorcanedo")
    urls = resolve(sc, "legislacao")
    assert urls == [
        "https://acessoainformacao.senadorcanedo.go.gov.br/cidadao/legislacao/portarias_psc",
        "https://acessoainformacao.senadorcanedo.go.gov.br/cidadao/legislacao/decretos_psc",
    ]


def test_legislacao_multi_rota_cristalina_4_subpaginas():
    """Cristalina: legislacao = leis + decretos + portarias + resolucoes."""
    cr = get_mun("cristalina")
    urls = resolve(cr, "legislacao")
    assert urls == [
        "https://acessoainformacao.cristalina.go.gov.br/cidadao/legislacao/leis",
        "https://acessoainformacao.cristalina.go.gov.br/cidadao/legislacao/decretos",
        "https://acessoainformacao.cristalina.go.gov.br/cidadao/legislacao/portarias",
        "https://acessoainformacao.cristalina.go.gov.br/cidadao/legislacao/resolucoes",
    ]


def test_legislacao_multi_rota_itumbiara_3_subpaginas():
    """Itumbiara: legislacao = portarias + decretos + resolucoes (sem sufixo)."""
    it = get_mun("itumbiara")
    urls = resolve(it, "legislacao")
    assert urls == [
        "https://acessoainformacao.itumbiara.go.gov.br/cidadao/legislacao/portarias",
        "https://acessoainformacao.itumbiara.go.gov.br/cidadao/legislacao/decretos",
        "https://acessoainformacao.itumbiara.go.gov.br/cidadao/legislacao/resolucoes",
    ]


def test_legislacao_saomiguel_so_nucleogov_sem_leis_externas():
    """Sao Miguel: legislacao concatena SO as sub-paginas NucleoGov (portarias/
    decretos com sufixo `_cnt`). As LEIS ficam num CMS externo (fora do host
    acessoainformacao) e estao FORA DO ESCOPO — nao entram na tabela."""
    sm = get_mun("saomigueldoaraguaia")
    urls = resolve(sm, "legislacao")
    assert urls == [
        "https://acessoainformacao.saomigueldoaraguaia.go.gov.br/cidadao/legislacao/portarias_cnt",
        "https://acessoainformacao.saomigueldoaraguaia.go.gov.br/cidadao/legislacao/decretos_cnt",
    ]
    # nenhuma URL aponta para o CMS institucional externo de leis.
    assert all("acessoainformacao." in u for u in urls)


def test_resolve_com_query_anexa_em_cada_url():
    t = get_mun("trindade")
    urls = resolve(t, "legislacao", {"ano": 2025})
    assert len(urls) == 3
    assert all("ano=2025" in u for u in urls)


def test_query_vazia_nao_polui_url():
    rv = get_mun("rioverde")
    urls = resolve(rv, "licitacoes", {"ano": "", "cnpj": None})
    assert all("?" not in u for u in urls)


def test_secao_invalida_keyerror():
    rv = get_mun("rioverde")
    with pytest.raises(KeyError, match="foo"):
        resolve(rv, "foo")


def test_aditamentos_indisponivel_nos_tres_primeiros():
    """aditamentos e secao valida no catalogo, mas Rio Verde nao tem rota propria
    (e subconjunto de contratos) -> SecaoIndisponivel, nao KeyError."""
    rv = get_mun("rioverde")
    with pytest.raises(SecaoIndisponivel, match="aditamentos"):
        resolve(rv, "aditamentos")


def test_aditamentos_resolve_nas_cidades_novas():
    """aditamentos tem rota propria (slug real `aditivos`) nas 3 cidades novas."""
    for slug in ("cristalina", "itumbiara", "saomigueldoaraguaia"):
        mun = get_mun(slug)
        urls = resolve(mun, "aditamentos")
        assert urls == [f"{mun.url_base}/cidadao/informacao/aditivos_cnt"], slug


def test_secao_indisponivel_para_municipio():
    """atas nao existe em Senador Canedo -> SecaoIndisponivel (nao inventa path)."""
    sc = get_mun("senadorcanedo")
    with pytest.raises(SecaoIndisponivel, match="atas"):
        resolve(sc, "atas")


def test_secoes_disponiveis_reflete_tabela():
    # Senador Canedo nao expoe `atas`; expoe legislacao, licitacoes, etc.
    disp = secoes_disponiveis("senadorcanedo")
    assert "atas" not in disp
    assert "licitacoes" in disp
    assert "legislacao" in disp
    # ordem canonica (subconjunto de SECOES)
    assert disp == [s for s in SECOES if s in disp]


def test_secoes_disponiveis_saomiguel_tem_todas():
    """Sao Miguel expoe as 10 secoes (unico com atas E aditamentos proprios)."""
    disp = secoes_disponiveis("saomigueldoaraguaia")
    assert disp == SECOES
    assert "atas" in disp and "aditamentos" in disp


def test_secoes_disponiveis_cristalina_sem_atas():
    """Cristalina tem aditamentos proprio, mas nao tem atas (so filtro)."""
    disp = secoes_disponiveis("cristalina")
    assert "aditamentos" in disp
    assert "atas" not in disp


def test_secoes_disponiveis_municipio_desconhecido_vazio():
    assert secoes_disponiveis("inexistente") == []


def test_resolve_municipio_sem_tabela_indisponivel():
    fake = Municipio(slug="foo", nome="Foo")
    with pytest.raises(SecaoIndisponivel):
        resolve(fake, "licitacoes")


def test_secoes_disponiveis_caldazinha_so_as_4_investigadas():
    """Caldazinha: so as 4 secoes das URLs fornecidas pelo dono foram
    investigadas ao vivo (item 3L54H3Sr-29); as demais nao tem rota."""
    disp = secoes_disponiveis("caldazinha")
    assert disp == ["contratos", "dispensas", "folha", "licitacoes"]
    with pytest.raises(SecaoIndisponivel, match="legislacao"):
        resolve(get_mun("caldazinha"), "legislacao")
