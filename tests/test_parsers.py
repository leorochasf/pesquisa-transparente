"""Testes para busca_go.nucleo.parsers — BUG-15: selecao de tabela.

O nucleogov costuma renderizar mais de uma <table> na mesma pagina (ex.:
tabela de legenda, tabela de dados, tabela oculta de medicao de largura
do grid JS). O parser antigo tratava a 1a <table> do HTML como "a"
tabela, misturando cabecalho de uma com linhas de outra. Os testes aqui
cobrem os dois padroes reais observados ao vivo no portal senadorcanedo:

(a) legenda/filtro (poucas colunas, 0 linhas de dados) + tabela de
    resultados auto-contida (cabecalho proprio na 1a linha).
(b) tabela so-cabecalho SEPARADA da tabela de dados (a tabela de dados
    so tem uma linha-molde vazia `template_row` + linhas reais).
"""

from pathlib import Path

from busca_go.nucleo.parsers import parse_tabela_generica

FIXTURES = Path(__file__).parent / "fixtures"


# ---------- sintetico (padrao a: legenda + tabela auto-contida) ----------


_HTML_LEGENDA_MAIS_DADOS = """
<html><body>
<table><tr><th>Tipo</th><th>Descricao</th></tr></table>
<table class="tb"><tr><td><div id="load"></div></td></tr></table>
<table>
  <tr><th>Objeto</th><th>Data</th><th>Valor</th></tr>
  <tr><td>Pregao 001/2025 - Aquisicao de mobiliario</td><td>10/01/2025</td><td>R$ 12.345,67</td></tr>
  <tr><td>Pregao 002/2025 - Servicos de limpeza</td><td>15/02/2025</td><td>R$ 8.900,00</td></tr>
</table>
</body></html>
"""


def test_ignora_tabela_de_legenda_e_usa_tabela_de_dados_auto_contida():
    """Padrao (a): a tabela de legenda (2 colunas, 0 linhas de dados) e a
    tabela de loading (1 linha vazia) nao devem contaminar o cabecalho da
    tabela de dados real (3 colunas, cabecalho proprio)."""
    itens = parse_tabela_generica(_HTML_LEGENDA_MAIS_DADOS, secao="licitacoes", fonte="test")
    assert len(itens) == 2
    assert itens[0].titulo == "Pregao 001/2025 - Aquisicao de mobiliario"
    assert itens[0].data == "10/01/2025"
    assert itens[0].valor == "R$ 12.345,67"
    assert itens[1].titulo == "Pregao 002/2025 - Servicos de limpeza"


# ---------- sintetico (padrao b: cabecalho em tabela separada) ----------


_HTML_CABECALHO_SEPARADO = """
<html><body>
<table><tr><th>Numero</th><th>Publicacao</th><th>Ementa</th></tr></table>
<table>
  <tr><td></td><td></td><td></td></tr>
  <tr><td>10.001/2026</td><td>01/03/2026</td><td>Dispoe sobre servidores publicos.</td></tr>
  <tr><td>10.000/2026</td><td>28/02/2026</td><td>Autoriza abertura de credito especial.</td></tr>
</table>
</body></html>
"""


def test_pareia_cabecalho_de_tabela_separada_com_mesma_contagem_de_colunas():
    """Padrao (b): a tabela de dados so tem uma linha-molde vazia
    (`template_row`) + linhas reais, sem cabecalho proprio. O cabecalho
    real vive em outra <table> com 1 unica linha e o MESMO numero de
    colunas — deve ser usado, e a linha-molde vazia nao deve virar um
    item fantasma nem consumir uma linha real como cabecalho falso."""
    itens = parse_tabela_generica(_HTML_CABECALHO_SEPARADO, secao="legislacao", fonte="test")
    assert len(itens) == 2
    assert itens[0].titulo == "10.001/2026"
    assert itens[0].data == "01/03/2026"
    assert itens[1].titulo == "10.000/2026"


def test_nao_pareia_cabecalho_com_contagem_de_colunas_diferente():
    """Uma tabela so-cabecalho com numero de colunas DIFERENTE da tabela
    de dados NAO deve ser usada como cabecalho (evita casar uma legenda
    de outro widget, ex.: 2 colunas, com dados de 3 colunas). Sem
    cabecalho compativel, cai no fallback (1a linha da propria tabela de
    dados vira cabecalho) — aqui so sobra 1 linha real apos filtrar a
    linha-molde vazia, entao o fallback (que exige >=2 linhas) nao tem
    dados suficientes e devolve lista vazia. O ponto do teste e negativo:
    a legenda de 2 colunas NUNCA deve ser usada como cabecalho aqui (se
    fosse usada incorretamente, sobrariam colunas descartadas/mapeadas
    errado em vez de lista vazia).
    """
    html = """
    <html><body>
    <table><tr><th>Tipo</th><th>Descricao</th></tr></table>
    <table>
      <tr><td></td><td></td><td></td></tr>
      <tr><td>10.001/2026</td><td>01/03/2026</td><td>Dispoe sobre servidores.</td></tr>
    </table>
    </body></html>
    """
    itens = parse_tabela_generica(html, secao="legislacao", fonte="test")
    assert itens == []


def test_nao_sequestra_cabecalho_quando_tabela_de_dados_tem_cabecalho_proprio():
    """A1 (regressao): tabela de dados com cabecalho PROPRIO (<th>) + uma
    tabela-irma de 1 linha com o MESMO numero de colunas (ex.: um box
    "Total de registros / 2 / atualizado"). O cabecalho da irma NAO pode
    ser sequestrado, e a 1a linha (cabecalho real) NAO pode virar item
    fantasma. Cenario exato reproduzido na revisao de segunda passada:
    antes do fix devolvia 3 itens com a coluna 'objeto' mapeada para
    'valor'; o correto sao 2 itens com colunas certas."""
    html = """
    <html><body>
    <table><tr><td>Total de registros</td><td>2</td><td>atualizado</td></tr></table>
    <table>
      <tr><th>Objeto</th><th>Data</th><th>Valor</th></tr>
      <tr><td>Pregao 001/2025</td><td>10/01/2025</td><td>R$ 100,00</td></tr>
      <tr><td>Pregao 002/2025</td><td>11/01/2025</td><td>R$ 200,00</td></tr>
    </table>
    </body></html>
    """
    itens = parse_tabela_generica(html, secao="licitacoes", fonte="test")
    assert len(itens) == 2  # sem item fantasma do cabecalho
    assert itens[0].titulo == "Pregao 001/2025"
    assert itens[0].data == "10/01/2025"
    assert itens[0].valor == "R$ 100,00"  # coluna 'valor' certa (nao 'objeto')
    assert itens[1].titulo == "Pregao 002/2025"
    assert itens[1].valor == "R$ 200,00"


def test_pagina_sem_tabela_de_dados_retorna_vazio():
    """So tabelas de legenda/loading, nenhuma com linha de dados real:
    deve devolver lista vazia (nao lanca excecao)."""
    html = """
    <html><body>
    <table><tr><th>Tipo</th><th>Descricao</th></tr></table>
    <table class="tb"><tr><td><div id="load"></div></td></tr></table>
    </body></html>
    """
    itens = parse_tabela_generica(html, secao="licitacoes", fonte="test")
    assert itens == []


def test_sem_tabela_no_html_retorna_vazio():
    assert parse_tabela_generica("<html><body>sem tabela aqui</body></html>", secao="x", fonte="test") == []


# ---------- fixture real (captura ao vivo, portal senadorcanedo) ----------


def test_fixture_real_senadorcanedo_legislacao():
    """Fixture reduzida capturada AO VIVO de
    https://acessoainformacao.senadorcanedo.go.gov.br/legislacao
    (2026-07-07, contexto de browser realista — ver client.py). Reproduz
    o padrao (b) real: tabela so-cabecalho "Numero/Publicacao/Ementa"
    separada da tabela de dados (que so tem uma linha-molde `template_row`
    vazia + linhas reais). Prova que o parser extrai itens reais, com
    cabecalho e linhas vindos das tabelas certas."""
    html = (FIXTURES / "senadorcanedo_legislacao.html").read_text(encoding="utf-8")
    itens = parse_tabela_generica(html, secao="legislacao", fonte="test")

    assert len(itens) == 4  # fixture reduzida: template_row + 4 leis reais
    for it in itens:
        assert it.titulo  # numero da lei (ex.: "8.361/2026")
        assert it.data  # data de publicacao real (dd/mm/aaaa)
        assert "col_2" in it.raw  # ementa (texto longo) cai em raw (nao mapeado por _classify)

    numeros = {it.titulo for it in itens}
    assert "8.361/2026" in numeros
    assert all(it.data == "07/07/2026" for it in itens)
