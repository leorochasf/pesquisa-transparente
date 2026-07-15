"""Smoke test para nucleo/routes.py"""
from busca_go.municipios import get as get_mun, Municipio
from busca_go.nucleo.routes import SECOES, resolve, PlataformaNaoSuportada

assert len(SECOES) == 10, SECOES

g = get_mun("goiania")
u = resolve(g, "licitacoes")
assert u == "https://acessoainformacao.goiania.go.gov.br/licitacao", u

u2 = resolve(g, "licitacoes", {"ano": 2025, "cnpj": "11.222.333/0001-81"})
assert "ano=2025" in u2, u2
assert "cnpj=11" in u2, u2
print("OK sgp licitacoes:", u2)

try:
    resolve(g, "foo")
    raise AssertionError
except KeyError as e:
    assert "foo" in str(e)
    print("OK keyerror em secao invalida")

fake = Municipio(slug="foo", nome="Foo", plataforma="frl")
try:
    resolve(fake, "licitacoes")
    raise AssertionError
except PlataformaNaoSuportada as e:
    assert "frl" in str(e)
    print("OK plataforma nao suportada")

print("ROUTES OK")
