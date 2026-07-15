"""Relatorio/export do dossie (blueprint P5, doc AUDITORIA/refatoracao/04-blueprint.md
§6.3, §2.3-2.4). Monta `relatorio.md` a partir do caso persistido (P2 -- `nucleo/casos.py`)
e do manifesto de evidencias (P3 -- `nucleo/evidencia.py`), SEM alterar nenhum dos dois.

O mesmo template serve a versao deterministica (este modulo) e a do agente (P4) --
so muda quem escreve a sintese em prosa. Regra de ouro: cada achado aponta para uma
evidencia do manifesto (link relativo + sha256) ou entra em Lacunas e ressalvas.
Nenhum campo ausente e inventado -- vira '—'.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..municipios import get as get_mun
from . import casos, evidencia

_TRACO = "—"

_SECAO_ROTULO = {
    "contratos": "Contrato",
    "dispensas": "Dispensa",
    "licitacoes": "Licitação",
    "despesas": "Despesa/Empenho",
    "folha": "Folha",
}

_MESES_ABREV = {
    "01": "jan", "02": "fev", "03": "mar", "04": "abr", "05": "mai", "06": "jun",
    "07": "jul", "08": "ago", "09": "set", "10": "out", "11": "nov", "12": "dez",
}


class RelatorioError(RuntimeError):
    """Falha ao montar/exportar o relatorio do caso."""


class CasoNaoEncontrado(RelatorioError):
    """Caso inexistente no banco de casos."""


class RelatorioPdfIndisponivel(RelatorioError):
    """Export a PDF requer uma biblioteca leve de renderizacao markdown->PDF
    (ex.: weasyprint, reportlab, fpdf2) que NAO esta instalada no venv deste
    projeto (checado no pacote P5 -- so ha `pikepdf`, que manipula PDF
    existente, nao renderiza texto). Por decisao do brief P5 ("senao
    markdown-only e registre -- NAO adicione dependencia pesada sem
    necessidade"), o export a PDF fica indisponivel ate uma dessas libs ser
    instalada; o relatorio markdown continua completo e utilizavel."""


class CaminhoEvidenciaInvalido(RelatorioError):
    """O caminho da evidencia resolveria para fora da pasta do caso -- recusado."""


# --------------------------------------------------------------------------- #
# Helpers de formatacao (nunca inventa dado -- ausente vira '—')
# --------------------------------------------------------------------------- #


def _nome_municipio(slug: str) -> str:
    try:
        return get_mun(slug).nome
    except KeyError:
        return slug


def _ou_traco(valor: Any) -> str:
    if valor is None:
        return _TRACO
    texto = str(valor).strip()
    return texto if texto else _TRACO


def _parse_valor(valor: Any) -> float | None:
    """'R$ 10.000,00' / '10000.00' / 10000 -> 10000.0. Retorna None se nao
    for possivel extrair um numero (nunca inventa/arredonda no escuro)."""
    if valor is None:
        return None
    texto = str(valor).strip()
    if not texto:
        return None
    m = re.search(r"(\d[\d.]*),(\d{2})\b", texto)
    if m:
        inteiro = m.group(1).replace(".", "")
        try:
            return float(f"{inteiro}.{m.group(2)}")
        except ValueError:
            return None
    m2 = re.search(r"\d+(?:\.\d+)?", texto)
    if m2:
        try:
            return float(m2.group(0))
        except ValueError:
            return None
    return None


def _fmt_valor(v: float) -> str:
    """1234.5 -> 'R$ 1.234,50' (separador de milhar '.', decimal ',')."""
    inteiro, decimal = f"{v:,.2f}".split(".")
    return f"R$ {inteiro.replace(',', '.')},{decimal}"


def _fmt_periodo(ano: Any, mes: Any) -> str:
    ano_s, mes_s = _ou_traco(ano), _ou_traco(mes)
    if ano_s == _TRACO or mes_s == _TRACO:
        return _TRACO
    mes_s = mes_s.zfill(2)
    abrev = _MESES_ABREV.get(mes_s, mes_s)
    return f"{abrev}/{ano_s}"


def _eh_folha(item: dict[str, Any]) -> bool:
    return item.get("secao") == "folha"


# --------------------------------------------------------------------------- #
# Evidencias por item (index O(1) a partir do manifesto -- fonte de verdade em disco)
# --------------------------------------------------------------------------- #


def _evidencias_por_item(manifesto: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    mapa: dict[str, list[dict[str, Any]]] = {}
    for ev in manifesto:
        item_id = ev.get("item_id") or ""
        if not item_id:
            continue
        mapa.setdefault(item_id, []).append(ev)
    return mapa


def _link_evidencia(ev: dict[str, Any]) -> str:
    caminho = ev.get("caminho_local") or ""
    rotulo = ev.get("rotulo") or ev.get("tipo") or "evidência"
    ev_id = ev.get("evidencia_id") or _TRACO
    sha = ev.get("sha256") or _TRACO
    sha_curto = sha if sha == _TRACO or len(sha) <= 12 else f"{sha[:12]}…"
    base = f"[{rotulo}]({caminho})" if caminho else rotulo
    return f"{base} · {ev_id} · sha256 `{sha_curto}`"


# --------------------------------------------------------------------------- #
# Achados por procedimento (§6.3)
# --------------------------------------------------------------------------- #


def _titulo_achado(item: dict[str, Any]) -> str:
    municipio = _nome_municipio(item["municipio"])
    if _eh_folha(item):
        raw = item.get("raw") or {}
        nome = _ou_traco(item.get("titulo") or raw.get("nome"))
        periodo = _fmt_periodo(raw.get("ano"), raw.get("mes"))
        return f"Folha — {nome} — {periodo} — {municipio}"
    rotulo_secao = _SECAO_ROTULO.get(item["secao"], item["secao"].capitalize())
    titulo = _ou_traco(item.get("titulo"))
    return f"{rotulo_secao} {titulo} — {municipio}"


def _linhas_achado(item: dict[str, Any], evidencias: list[dict[str, Any]]) -> list[str]:
    linhas: list[str] = []
    raw = item.get("raw") or {}
    if _eh_folha(item):
        proventos = _parse_valor(raw.get("proventos"))
        descontos = _parse_valor(raw.get("descontos"))
        liquido_raw = _parse_valor(raw.get("liquido"))
        liquido = liquido_raw if liquido_raw is not None else _parse_valor(item.get("valor"))
        p = _fmt_valor(proventos) if proventos is not None else _TRACO
        d = _fmt_valor(descontos) if descontos is not None else _TRACO
        l = _fmt_valor(liquido) if liquido is not None else _TRACO
        linhas.append(f"- Proventos {p} · Descontos {d} · Líquido {l}")
    else:
        fornecedor = _ou_traco(raw.get("fornecedor"))
        valor = _parse_valor(item.get("valor"))
        valor_s = _fmt_valor(valor) if valor is not None else _ou_traco(item.get("valor"))
        data = _ou_traco(item.get("data"))
        linhas.append(f"- Fornecedor: {fornecedor} · Valor: {valor_s} · Data: {data}")
    rotulo_lastro = "Lastro" if _eh_folha(item) else "Documentos"
    if evidencias:
        links = " · ".join(_link_evidencia(e) for e in evidencias)
        linhas.append(f"- {rotulo_lastro}: {links}")
    else:
        linhas.append(f"- {rotulo_lastro}: **[não verificado]** — nenhuma evidência coletada para este item.")
    return linhas


def _montar_achados(itens: list[dict[str, Any]], evid_por_item: dict[str, list[dict[str, Any]]]) -> str:
    if not itens:
        return "Nenhum item persistido neste caso ainda.\n"
    blocos: list[str] = []
    for item in itens:
        blocos.append(f"### {_titulo_achado(item)}")
        blocos.extend(_linhas_achado(item, evid_por_item.get(item["id"], [])))
    return "\n".join(blocos) + "\n"


# --------------------------------------------------------------------------- #
# Sintese
# --------------------------------------------------------------------------- #


def _montar_sintese(itens: list[dict[str, Any]]) -> str:
    total = len(itens)
    if total == 0:
        return "Nenhum achado persistido neste caso ainda — dispare uma busca (`POST /api/casos/{id}/pesquisar`) ou anexe itens manualmente.\n"
    por_secao: dict[str, int] = {}
    municipios: set[str] = set()
    for item in itens:
        por_secao[item["secao"]] = por_secao.get(item["secao"], 0) + 1
        municipios.add(item["municipio"])
    resumo_secoes = ", ".join(
        f"{qtd} de {_SECAO_ROTULO.get(sec, sec)}" for sec, qtd in sorted(por_secao.items())
    )
    municipios_nomes = ", ".join(sorted(_nome_municipio(m) for m in municipios))
    return (
        f"Foram encontrados **{total}** item(ns) neste caso ({resumo_secoes}), "
        f"em {municipios_nomes}.\n"
    )


# --------------------------------------------------------------------------- #
# Quantificacao (mes a mes + total -- historia 2 do blueprint, quando aplicavel)
# --------------------------------------------------------------------------- #


def _montar_quantificacao(itens: list[dict[str, Any]]) -> str:
    folha = [it for it in itens if _eh_folha(it)]
    if not folha:
        return "Não aplicável a este caso — nenhum item de folha para quantificar.\n"
    linhas = ["| Servidor | Competência | Líquido |", "|---|---|---|"]
    total = 0.0
    algum_nao_parseado = False
    for item in folha:
        raw = item.get("raw") or {}
        nome = _ou_traco(item.get("titulo") or raw.get("nome"))
        periodo = _fmt_periodo(raw.get("ano"), raw.get("mes"))
        liquido_raw = _parse_valor(raw.get("liquido"))
        liquido = liquido_raw if liquido_raw is not None else _parse_valor(item.get("valor"))
        if liquido is None:
            linhas.append(f"| {nome} | {periodo} | **[não verificado]** |")
            algum_nao_parseado = True
        else:
            linhas.append(f"| {nome} | {periodo} | {_fmt_valor(liquido)} |")
            total += liquido
    linhas.append(f"| **Total** | | **{_fmt_valor(total)}** |")
    texto = "\n".join(linhas) + "\n"
    if algum_nao_parseado:
        texto += "\n_Alguns valores não puderam ser lidos do dado bruto — marcados **[não verificado]** e excluídos do total acima._\n"
    return texto


# --------------------------------------------------------------------------- #
# Lacunas e ressalvas
# --------------------------------------------------------------------------- #


def _montar_lacunas(
    caso_id: str,
    itens: list[dict[str, Any]],
    evid_por_item: dict[str, list[dict[str, Any]]],
) -> str:
    linhas: list[str] = []
    sem_evidencia = [it for it in itens if not evid_por_item.get(it["id"])]
    for item in sem_evidencia:
        linhas.append(
            f"- {_titulo_achado(item)}: nenhuma evidência coletada — **[não verificado]**."
        )
    pendentes = evidencia.ler_pendentes(caso_id)
    if pendentes:
        linhas.append(
            f"- {len(pendentes)} anexo(s) não baixado(s) por atingir o teto de "
            f"{evidencia.TETO_PDFS_CASO} PDFs do caso — disponíveis para expansão "
            "(ver `evidencias_pendentes.jsonl`)."
        )
    if not linhas:
        return "Nenhuma lacuna identificada — todo item deste caso tem ao menos uma evidência coletada.\n"
    return "\n".join(linhas) + "\n"


# --------------------------------------------------------------------------- #
# Indice de evidencias
# --------------------------------------------------------------------------- #


def _montar_indice_evidencias(manifesto: list[dict[str, Any]]) -> str:
    if not manifesto:
        return "Nenhuma evidência coletada neste caso ainda.\n"
    linhas = ["| Evidência | Tipo | Arquivo | Origem | sha256 |", "|---|---|---|---|---|"]
    for ev in manifesto:
        ev_id = ev.get("evidencia_id", _TRACO)
        tipo = ev.get("tipo", _TRACO)
        caminho = ev.get("caminho_local") or ""
        rotulo = ev.get("rotulo") or caminho or _TRACO
        arquivo = f"[{rotulo}]({caminho})" if caminho else rotulo
        origem = f"{ev.get('municipio', _TRACO)}/{ev.get('secao', _TRACO)}"
        sha = ev.get("sha256", _TRACO)
        linhas.append(f"| {ev_id} | {tipo} | {arquivo} | {origem} | `{sha}` |")
    return "\n".join(linhas) + "\n"


# --------------------------------------------------------------------------- #
# Cabecalho + montagem final (template §6.3)
# --------------------------------------------------------------------------- #


def _fmt_alvos(alvos: dict[str, Any]) -> str:
    partes = []
    for chave, rotulo in (("nome", "nome"), ("cnpj", "CNPJ"), ("servidor", "servidor")):
        if alvos.get(chave):
            partes.append(f"{rotulo}: {alvos[chave]}")
    if alvos.get("periodos"):
        partes.append(f"períodos: {', '.join(str(p) for p in alvos['periodos'])}")
    return " · ".join(partes) if partes else _TRACO


def _fmt_data(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def gerar_relatorio_markdown(caso_id: str, db: Any | None = None) -> str:
    """Monta o `relatorio.md` do caso (template §6.3) a partir do que ja esta
    persistido -- NUNCA dispara busca nova. Le itens/anotacoes via
    `nucleo/casos.py` (P2) e evidencias via o MANIFESTO em disco (`nucleo/
    evidencia.py`, P3 -- fonte de verdade do dossie, doc §2.4).

    Raises:
        CasoNaoEncontrado: `caso_id` nao existe no banco de casos.
    """
    caso = casos.obter_caso(caso_id, db=db)
    if caso is None:
        raise CasoNaoEncontrado(f"Caso '{caso_id}' não encontrado.")
    itens = caso["itens"]
    manifesto = evidencia.ler_manifesto(caso_id)
    evid_por_item = _evidencias_por_item(manifesto)
    municipios_nomes = ", ".join(_nome_municipio(m) for m in caso["municipios"])

    partes = [
        f"# Dossiê — {caso['titulo']}",
        f"Tipo: {caso['tipo']} · Municípios: {municipios_nomes} · "
        f"Gerado em: {_fmt_data(time.time())} · "
        f"Alvos: {_fmt_alvos(caso['alvos'])}",
        "",
        "## Síntese",
        _montar_sintese(itens),
        "## Achados por procedimento",
        _montar_achados(itens, evid_por_item),
        "## Quantificação (quando aplicável)",
        _montar_quantificacao(itens),
        "## Lacunas e ressalvas",
        _montar_lacunas(caso_id, itens, evid_por_item),
        "## Índice de evidências",
        _montar_indice_evidencias(manifesto),
    ]
    return "\n".join(partes)


def caminho_relatorio(caso_id: str) -> Path:
    """`data/casos/<caso_id>/relatorio.md` (blueprint §2.4)."""
    return evidencia.caminho_caso(caso_id) / "relatorio.md"


def salvar_relatorio(caso_id: str, db: Any | None = None) -> Path:
    """Gera e grava `relatorio.md` em disco (regenerável -- sobrescreve).
    Retorna o caminho absoluto do arquivo escrito."""
    texto = gerar_relatorio_markdown(caso_id, db=db)
    caminho = caminho_relatorio(caso_id)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(texto, encoding="utf-8")
    return caminho


_SUBSTITUICOES_PDF = {
    "—": "-",
    "–": "-",
    "…": "...",
    "“": '"',
    "”": '"',
    "’": "'",
    "•": "-",
}


_TOKEN_MAX = 40
_TOKEN_MAX_TABELA = 70  # W1-F2: sha256 tem 64 chars -- precisa sair inteiro, sem quebra.

_LINK_INLINE_RE = re.compile(r"\[([^\[\]]+)\]\(([^()]+)\)")
_ITALICO_INLINE_RE = re.compile(r"(?<!\w)_(.+?)_(?!\w)")


def _resolver_inline_pdf(linha: str) -> str:
    """W1-F1: `fpdf2` com fonte core não interpreta marcadores markdown
    inline -- `**negrito**`, `_itálico_` e `` `código` `` saíam literais no
    PDF, e links `[texto](url)` idem. Resolve antes do `multi_cell`: link
    vira 'texto (url)'; negrito/itálico/código são apenas removidos (o
    texto em si -- incluindo o literal `[não verificado]` -- continua
    intacto, só sem os marcadores; a honestidade do conteúdo não muda, só
    o ruído visual)."""
    linha = _LINK_INLINE_RE.sub(r"\1 (\2)", linha)
    linha = linha.replace("**", "").replace("`", "")
    linha = _ITALICO_INLINE_RE.sub(r"\1", linha)
    return linha


def _sanitizar_linha_pdf(linha: str) -> str:
    """`fpdf2` com fonte core (Helvetica/Courier) só suporta Latin-1. Os
    acentos do português cabem em Latin-1, mas pontuação tipográfica
    (travessão, reticências, aspas curvas) não -- normaliza para o
    equivalente ascii e, para qualquer sobra inesperada, cai em
    'latin-1'/replace (degrada o glifo, nunca quebra a geração)."""
    for original, novo in _SUBSTITUICOES_PDF.items():
        linha = linha.replace(original, novo)
    return linha.encode("latin-1", errors="replace").decode("latin-1")


def _quebrar_tokens_longos(linha: str, max_len: int = _TOKEN_MAX) -> str:
    """Token sem espaço mais longo que `max_len` (sha256, URL, caminho) não
    tem onde quebrar e faria o `multi_cell` (modo padrão de quebra por
    palavra) estourar a largura da página -- insere espaços a cada
    `max_len` chars para abrir pontos de quebra. `WrapMode.CHAR` do fpdf2
    resolveria isso nativamente mas trava (loop infinito observado na versão
    2.8.7 instalada) -- preferimos esta solução simples e testada."""
    return " ".join(
        " ".join(token[i : i + max_len] for i in range(0, len(token), max_len)) if len(token) > max_len else token
        for token in linha.split(" ")
    )


def caminho_relatorio_pdf(caso_id: str) -> Path:
    """`data/casos/<caso_id>/relatorio.pdf` (blueprint §2.4, irmão de
    `caminho_relatorio`)."""
    return evidencia.caminho_caso(caso_id) / "relatorio.pdf"


def exportar_pdf(caso_id: str, db: Any | None = None) -> Path:
    """Exporta o relatorio.md do caso para PDF (fpdf2 -- pure-Python, sem
    dependência nativa; roda em Windows sem GTK). Títulos (`#`/`##`/`###`)
    viram destaque; linhas de tabela markdown (`|...|`) degradam para fonte
    monoespaçada -- legibilidade honesta é preferida a tentar recriar a
    grade da tabela. Salva `data/casos/<id>/relatorio.pdf` (sobrescreve) e
    retorna o caminho."""
    try:
        from fpdf import FPDF
    except ImportError as exc:
        raise RelatorioPdfIndisponivel(
            "Export a PDF indisponível: dependência 'fpdf2' não instalada "
            "neste projeto. Use `?formato=md`."
        ) from exc

    texto = gerar_relatorio_markdown(caso_id, db=db)
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(15, 15, 15)
    pdf.add_page()

    # multi_cell(w=0, ...) usa a largura RESTANTE a partir de `pdf.x` -- o
    # default `new_x=XPos.RIGHT` deixa `pdf.x` colado na margem direita
    # apos a chamada anterior, entao a proxima com w=0 calcula largura ~0 e
    # o fpdf2 explode em FPDFException ("Not enough horizontal space").
    # `new_x="LMARGIN"` volta o cursor pra margem esquerda a cada linha.
    for linha in texto.split("\n"):
        resolvida = _sanitizar_linha_pdf(_resolver_inline_pdf(linha))
        eh_tabela = resolvida.startswith("|")
        limpa = _quebrar_tokens_longos(resolvida, max_len=_TOKEN_MAX_TABELA if eh_tabela else _TOKEN_MAX)
        if limpa.startswith("### "):
            pdf.set_font("Helvetica", "B", 12)
            pdf.multi_cell(0, 7, limpa[4:], new_x="LMARGIN")
        elif limpa.startswith("## "):
            pdf.set_font("Helvetica", "B", 14)
            pdf.multi_cell(0, 8, limpa[3:], new_x="LMARGIN")
        elif limpa.startswith("# "):
            pdf.set_font("Helvetica", "B", 16)
            pdf.multi_cell(0, 9, limpa[2:], new_x="LMARGIN")
        elif limpa.startswith("|"):
            pdf.set_font("Courier", "", 7)
            pdf.multi_cell(0, 4, limpa, new_x="LMARGIN")
        elif not limpa:
            pdf.ln(3)
        else:
            pdf.set_font("Helvetica", "", 10)
            pdf.multi_cell(0, 6, limpa, new_x="LMARGIN")

    caminho = caminho_relatorio_pdf(caso_id)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(bytes(pdf.output()))
    return caminho


# --------------------------------------------------------------------------- #
# Servir arquivo de evidencia (P5, endpoint de download) -- valida path SEMPRE
# --------------------------------------------------------------------------- #


def resolver_arquivo_evidencia(caso_id: str, evidencia_id: str) -> tuple[Path, str, str] | None:
    """Localiza o arquivo de UMA evidencia do manifesto e valida que o caminho
    resolvido continua DENTRO de `data/casos/<caso_id>/` (defesa contra path
    traversal -- nunca serve arquivo fora do dossie do caso).

    Retorna `(caminho_absoluto, content_type, nome_arquivo)` ou `None` se a
    evidencia nao existe no manifesto ou o arquivo nao esta (mais) em disco.

    Raises:
        CaminhoEvidenciaInvalido: o `caminho_local` da evidencia resolveria
            para fora da pasta do caso (nunca deveria acontecer com entradas
            gravadas por `evidencia.registrar_evidencia`, mas e checado aqui
            mesmo assim -- defesa em profundidade).
    """
    base = evidencia.caminho_caso(caso_id).resolve()
    for ev in evidencia.ler_manifesto(caso_id):
        if ev.get("evidencia_id") != evidencia_id:
            continue
        caminho_relativo = ev.get("caminho_local") or ""
        candidato = (base / caminho_relativo).resolve()
        try:
            candidato.relative_to(base)
        except ValueError:
            raise CaminhoEvidenciaInvalido(
                f"Caminho da evidência '{evidencia_id}' resolveria para fora do dossie do caso."
            )
        if not candidato.is_file():
            return None
        content_type = ev.get("content_type") or "application/octet-stream"
        return candidato, content_type, candidato.name
    return None


__all__ = [
    "RelatorioError",
    "CasoNaoEncontrado",
    "RelatorioPdfIndisponivel",
    "CaminhoEvidenciaInvalido",
    "gerar_relatorio_markdown",
    "caminho_relatorio",
    "caminho_relatorio_pdf",
    "salvar_relatorio",
    "exportar_pdf",
    "resolver_arquivo_evidencia",
]
