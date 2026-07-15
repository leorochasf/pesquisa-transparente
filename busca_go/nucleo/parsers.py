"""Parsers HTML -> dataclasses para nucleogov.

O nucleogov (Nucleo Gov / SIGEP / Fiorilli / CENTI / SGP / FRL / MG / CNT)
tem variacoes entre municipios. Este modulo expoe:

- ItemTransparencia: dataclass Pydantic com os campos minimos.
- ParseError:        excecao especifica.
- parse_tabela_generica: parser generico (best-effort) que extrai cada
                        <table> da pagina separadamente e escolhe a
                        tabela de DADOS por heuristica (ver
                        _select_data_table) — o nucleogov costuma
                        renderizar mais de uma <table> na mesma pagina.

AJUSTE DE SELETORES: se mudar o markup, altere APENAS este arquivo.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any

from pydantic import BaseModel, Field


# ---------- modelos ----------

class ItemTransparencia(BaseModel):
    """Item generico de transparencia publica."""

    titulo: str = ""
    data: str = ""
    valor: str = ""
    link: str = ""
    fonte: str = ""
    secao: str = ""
    raw: dict[str, str] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


class ParseError(Exception):
    """HTML nao corresponde ao esperado."""


# ---------- regex de campos opcionais ----------

_DATA_BR = re.compile(r"\b(\d{2}/\d{2}/\d{4})\b")
_VALOR_BR = re.compile(r"R\$\s*[\d\.\,]+(?:,\d{2})?", re.IGNORECASE)
_HREF = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.IGNORECASE)


# ---------- extracao de tabela HTML sem dependencia externa ----------


class _TableExtractor(HTMLParser):
    """Extrai CADA `<table>` de nivel superior da pagina como uma matriz
    de strings independente (uma lista de tabelas, nao uma lista unica de
    linhas). O nucleogov costuma renderizar mais de uma `<table>` na
    mesma pagina (ex.: legenda/filtros ao lado da tabela de resultados);
    misturar as linhas de todas sob um unico cabecalho corrompe o parse.

    Mantem-se minimalista: nao tenta renderizar atributos complexos nem
    CSS. O nucleogov gera HTML server-side, entao a tabela vem estavel.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._tables: list[list[list[str]]] = []
        # Paralelo a _tables: para cada linha, True se ela e uma linha de
        # CABECALHO (todas as celulas <th>, nenhuma <td>). Usado para
        # distinguir tabela de dados com cabecalho proprio (padrao a) de
        # tabela de dados sem cabecalho (padrao b) — ver _select_data_table.
        self._header_flags: list[list[bool]] = []
        self._current_rows: list[list[str]] | None = None
        self._current_flags: list[bool] | None = None
        self._current_row: list[str] | None = None
        self._current_cell: list[str] | None = None
        self._row_has_th = False
        self._row_has_td = False
        self._depth_table = 0
        self._depth_cell = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        if t == "table":
            if self._depth_table == 0:
                self._current_rows = []
                self._current_flags = []
            self._depth_table += 1
            return
        if self._depth_table == 0:
            return
        if t == "tr":
            self._current_row = []
            self._row_has_th = False
            self._row_has_td = False
        elif t in ("th", "td"):
            if t == "th":
                self._row_has_th = True
            else:
                self._row_has_td = True
            self._current_cell = []
            self._depth_cell += 1
        elif t == "a" and self._current_cell is not None:
            href = dict(attrs).get("href", "")
            if href:
                # Anexa o href ao conteudo da celula; parser de coluna usa
                # o ultimo href presente no texto.
                self._current_cell.append(f" HREF={href}")

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if self._depth_table == 0:
            return
        if t == "table":
            self._depth_table -= 1
            if self._depth_table == 0 and self._current_rows is not None:
                self._tables.append(self._current_rows)
                self._header_flags.append(self._current_flags or [])
                self._current_rows = None
                self._current_flags = None
        elif t == "tr" and self._current_row is not None:
            if self._current_rows is not None:
                self._current_rows.append(self._current_row)
            if self._current_flags is not None:
                self._current_flags.append(self._row_has_th and not self._row_has_td)
            self._current_row = None
        elif t in ("th", "td") and self._current_cell is not None:
            self._depth_cell -= 1
            if self._depth_cell == 0:
                cell_text = "".join(self._current_cell).strip()
                if self._current_row is not None:
                    self._current_row.append(cell_text)
                self._current_cell = None

    def handle_data(self, data: str) -> None:
        if self._current_cell is not None:
            self._current_cell.append(data)

    def handle_entityref(self, name: str) -> None:
        if self._current_cell is not None:
            # convert_charrefs ja trata a maioria; fallback defensivo.
            self._current_cell.append(self.unescape(f"&{name};"))

    @property
    def tables(self) -> list[list[list[str]]]:
        return self._tables

    @property
    def header_flags(self) -> list[list[bool]]:
        """Paralelo a `tables`: por linha, True se for linha de cabecalho (<th>)."""
        return self._header_flags


# ---------- mapeamento de colunas ----------


_COL_TITULO = ("objeto", "descricao", "descrição", "titulo", "título", "nome", "item", "licitacao", "licitação", "contrato", "numero", "número")
_COL_DATA = ("data", "dt", "publicacao", "publicação", "data_publicacao")
_COL_VALOR = ("valor", "vlr", "total", "montante", "preco", "preço")
_COL_LINK = ("link", "detalhe", "edital", "anexo", "arquivo", "documento")


def _classify(header: str) -> str:
    h = header.strip().lower()
    if any(c in h for c in _COL_LINK):
        return "link"
    if any(c in h for c in _COL_VALOR):
        return "valor"
    if any(c in h for c in _COL_DATA):
        return "data"
    if any(c in h for c in _COL_TITULO):
        return "titulo"
    return "raw"


def _extrair_link(texto_celula: str) -> str:
    """Se a celula recebeu o marcador ' HREF=...', retorna o href."""
    m = _HREF.search(texto_celula)
    if m:
        return m.group(1)
    return ""


def _valor_para_campo(celula: str, data_celula: str) -> str:
    """Tenta extrair data e valor de uma celula quando colunas especificas
    nao foram identificadas (best-effort)."""
    return celula  # default: usa a celula como veio


def _select_data_table(
    tabelas: list[list[list[str]]],
    header_flags: list[list[bool]] | None = None,
) -> tuple[list[str], list[list[str]]] | None:
    """Escolhe, entre as `<table>` da pagina, qual e a tabela de DADOS —
    e de onde vem o cabecalho dela.

    O nucleogov costuma renderizar mais de uma `<table>` na mesma pagina.
    Observado ao vivo (captura real, secoes licitacoes/legislacao) duas
    variacoes que uma heuristica "so a 1a tabela" (comportamento antigo,
    BUG-15) corrompe:

    (a) Tabela de legenda/filtro (poucas colunas, 0 linhas de dados) +
        tabela de resultados real (cabecalho PROPRIO na 1a linha, <th>).
    (b) Tabela so-cabecalho (1 unica linha <th>, ex.: "Numero/Publicacao/
        Ementa") SEPARADA da tabela de dados — a tabela de dados em si
        so tem uma linha-molde vazia (`template_row`, usada pelo grid JS
        para clonar) + as linhas reais <td>, sem cabecalho proprio.
    Em ambos os casos ha ainda uma 3a tabela oculta (`visibility:hidden`,
    usada pelo grid para medir largura de coluna) com celulas vazias.

    Heuristica:
    1. Para cada tabela, filtra linhas totalmente vazias (cobre o
       `template_row` do caso b) e calcula um "volume" = numero de
       linhas restantes x numero de colunas. A tabela de DADOS e a de
       maior volume (tabelas de legenda/medicao tem poucas colunas e
       quase nenhuma linha).
    2. Cabecalho:
       - Se a tabela de dados vencedora TEM cabecalho proprio (1a linha
         nao-vazia e uma linha <th>, caso a), usa essa 1a linha como
         cabecalho e o RESTANTE como dados. NUNCA consulta tabelas-irmas
         nesse caso — isso evitava o sequestro de cabecalho + item
         fantasma quando existia uma tabela-irma de mesma largura (A1).
       - Caso contrario (tabela de dados SEM cabecalho proprio, caso b):
         se OUTRA tabela tem exatamente 1 linha nao-vazia com o MESMO
         numero de colunas, usa essa linha como cabecalho e TODAS as
         linhas da tabela de dados como dados (nenhuma linha e cabecalho
         proprio, entao nao ha fantasma). O numero de colunas evita casar
         com uma legenda de esquema diferente (ex.: "Tipo/Descricao" de 2
         colunas nao serve para uma tabela de dados de 5 colunas).
       - Sem cabecalho externo compativel, cai no fallback auto-contido
         (1a linha da propria tabela vira cabecalho).

    Retorna (header, data_rows), ou None se nenhuma tabela tiver
    conteudo aproveitavel.
    """
    if header_flags is None:
        header_flags = [[] for _ in tabelas]

    # Filtra linhas totalmente vazias mantendo as flags de cabecalho alinhadas.
    tabelas_filtradas: list[list[list[str]]] = []
    flags_filtradas: list[list[bool]] = []
    for t, flags in zip(tabelas, header_flags):
        linhas: list[list[str]] = []
        fl: list[bool] = []
        for i, r in enumerate(t):
            if any(c.strip() for c in r):
                linhas.append(r)
                fl.append(flags[i] if i < len(flags) else False)
        tabelas_filtradas.append(linhas)
        flags_filtradas.append(fl)

    melhor_idx: int | None = None
    melhor_score = 0
    for i, linhas in enumerate(tabelas_filtradas):
        if not linhas:
            continue
        ncols = max(len(r) for r in linhas)
        score = len(linhas) * ncols
        if score > melhor_score:
            melhor_score = score
            melhor_idx = i

    if melhor_idx is None:
        return None

    linhas_dados = tabelas_filtradas[melhor_idx]
    flags_dados = flags_filtradas[melhor_idx]
    ncols_dados = max(len(r) for r in linhas_dados)

    # Caso (a): a tabela de dados tem cabecalho PROPRIO (1a linha <th>).
    # Usa a propria 1a linha como cabecalho; nunca consulta tabelas-irmas.
    if flags_dados and flags_dados[0]:
        if len(linhas_dados) < 2:
            return None
        return linhas_dados[0], linhas_dados[1:]

    # Caso (b): tabela de dados SEM cabecalho proprio. Procura o cabecalho
    # numa tabela-irma de 1 linha e MESMO numero de colunas.
    for i, linhas in enumerate(tabelas_filtradas):
        if i == melhor_idx:
            continue
        if len(linhas) == 1 and len(linhas[0]) == ncols_dados:
            return linhas[0], linhas_dados

    # Sem cabecalho externo compativel: fallback auto-contido.
    if len(linhas_dados) < 2:
        return None
    return linhas_dados[0], linhas_dados[1:]


# ---------- API publica ----------


def parse_tabela_generica(html: str, secao: str, fonte: str) -> list[ItemTransparencia]:
    """Extrai cada `<table>` da pagina e mapeia a tabela de DADOS para itens.

    Estrategia:
    1. Extrai cada `<table>` como matriz de strings independente.
    2. Escolhe a tabela de dados via `_select_data_table` (ver docstring).
    3. Primeira linha nao-vazia da tabela escolhida vira cabecalho.
    4. Linhas seguintes viram itens; cada coluna mapeada para um campo
       do ItemTransparencia conforme `_classify`.

    Retorna lista vazia se nao houver tabela de dados utilizavel.
    """
    if not html or "<table" not in html.lower():
        return []

    extr = _TableExtractor()
    try:
        extr.feed(html)
    except Exception as exc:  # parser defensivo
        raise ParseError(f"falha ao parsear HTML: {exc}") from exc

    selecionada = _select_data_table(extr.tables, extr.header_flags)
    if selecionada is None:
        return []
    header, data_rows = selecionada
    mapa = [_classify(h) for h in header]

    itens: list[ItemTransparencia] = []
    for row in data_rows:
        item = ItemTransparencia(fonte=fonte, secao=secao)
        raw: dict[str, str] = {}
        for idx, cell in enumerate(row):
            if idx >= len(mapa):
                break
            campo = mapa[idx]
            cell_clean = cell.strip()
            if not cell_clean:
                continue
            if campo == "titulo":
                item.titulo = cell_clean
            elif campo == "data":
                item.data = cell_clean
            elif campo == "valor":
                item.valor = cell_clean
            elif campo == "link":
                href = _extrair_link(cell_clean)
                if href:
                    item.link = href
                elif cell_clean:
                    item.link = cell_clean
            else:
                raw[f"col_{idx}"] = cell_clean
        # Fallbacks por regex (se a coluna nao foi mapeada)
        if not item.data:
            for cell in row:
                m = _DATA_BR.search(cell)
                if m:
                    item.data = m.group(1)
                    break
        if not item.valor:
            for cell in row:
                m = _VALOR_BR.search(cell)
                if m:
                    item.valor = m.group(0)
                    break
        item.raw = raw
        # Se nao capturamos titulo, usa a primeira celula nao-vazia
        if not item.titulo:
            for cell in row:
                if cell.strip():
                    item.titulo = cell.strip()
                    break
        # Item precisa de pelo menos titulo ou data para ser util
        if item.titulo or item.data:
            itens.append(item)
    return itens


__all__ = ["ItemTransparencia", "ParseError", "parse_tabela_generica"]
