"""Testes para nucleo.sections."""

from busca_go.municipios import get as get_mun
from busca_go.nucleo.routes import resolve
from busca_go.nucleo.sections import Contratos, Despesas, Licitacoes, SECTIONS


def test_registry_tem_3_secoes():
    assert set(SECTIONS) == {"licitacoes", "contratos", "despesas"}


def test_build_url_consistente_com_routes():
    """Section.build_url deve bater com routes.resolve (lista de URLs)."""
    mun = get_mun("rioverde")
    for cls in [Licitacoes, Contratos, Despesas]:
        sec = cls()
        url = sec.build_url(mun, {"ano": 2025})
        expected = resolve(mun, sec.slug, {"ano": 2025})
        assert url == expected, (sec.slug, url, expected)
        assert isinstance(url, list)


def test_validar_filtros_ok():
    sec = Licitacoes()
    erros = sec.validar_filtros({"ano": 2025, "modalidade": "pregao"})
    assert erros == {}


def test_validar_filtros_rejeita_desconhecido():
    sec = Licitacoes()
    erros = sec.validar_filtros({"ano": 2025, "foo": "bar"})
    assert "foo" in erros
    assert "aceitos" in erros["foo"]


def test_descricoes_presentes():
    for cls in [Licitacoes, Contratos, Despesas]:
        sec = cls()
        assert sec.descricao, f"{cls.__name__} sem descricao"
        assert sec.slug, f"{cls.__name__} sem slug"
        assert isinstance(sec.filtros, dict)