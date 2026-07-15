"""Testes do gerador de relatorio (`busca_go/nucleo/relatorio.py`) com caso
sintetico -- sem rede, sem Chromium. DB isolado em `tmp_path` + DATA_DIR
isolado (manifesto/dossie em disco tambem isolados do `data/` real)."""

from __future__ import annotations

import pytest
from pypdf import PdfReader

from busca_go.db import DB
from busca_go.nucleo import casos, evidencia, relatorio


@pytest.fixture
def db(tmp_path) -> DB:
    return DB(db_path=tmp_path / "casos-teste.db")


@pytest.fixture(autouse=True)
def _data_dir_isolado(tmp_path, monkeypatch):
    monkeypatch.setattr(evidencia.settings, "DATA_DIR", tmp_path)


def _caso_com_contrato(db: DB) -> dict:
    caso = casos.criar_caso(
        titulo="Escritório X — dispensa",
        tipo="dispensa_advocacia",
        alvos={"nome": "Escritorio X", "cnpj": "02292266000180"},
        municipios=["senadorcanedo"],
        db=db,
    )
    item = {
        "titulo": "0343/26",
        "fornecedor": "Escritorio X Advocacia",
        "documento": "02292266000180",
        "valor": "R$ 10.000,00",
        "data": "2026-01-10",
        "ref_registro": {"id": "abc123", "numero": "0343", "ano": "26"},
        "raw": {"fornecedor": "Escritorio X Advocacia"},
    }
    casos.adicionar_itens_da_busca(caso["id"], "senadorcanedo", "contratos", [item], db=db)
    return casos.obter_caso(caso["id"], db=db)


def test_relatorio_de_caso_inexistente_levanta_erro(db: DB):
    with pytest.raises(relatorio.CasoNaoEncontrado):
        relatorio.gerar_relatorio_markdown("caso_nao_existe", db=db)


def test_relatorio_estrutura_basica_e_lacuna_sem_evidencia(db: DB):
    caso = _caso_com_contrato(db)
    md = relatorio.gerar_relatorio_markdown(caso["id"], db=db)

    assert md.startswith(f"# Dossiê — {caso['titulo']}")
    assert "## Síntese" in md
    assert "## Achados por procedimento" in md
    assert "## Quantificação (quando aplicável)" in md
    assert "## Lacunas e ressalvas" in md
    assert "## Índice de evidências" in md
    assert "### Contrato 0343/26 — Senador Canedo" in md
    assert "Fornecedor: Escritorio X Advocacia" in md
    assert "Valor: R$ 10.000,00" in md
    # Sem evidencia coletada -- vira lacuna explicita, nao dado inventado.
    assert "[não verificado]" in md
    assert "nenhuma evidência coletada" in md


def test_relatorio_com_evidencia_traz_link_relativo_e_sha256(db: DB):
    caso = _caso_com_contrato(db)
    item_id = caso["itens"][0]["id"]
    evidencia.registrar_evidencia(
        caso["id"],
        {
            "item_id": item_id,
            "tipo": "pdf",
            "municipio": "senadorcanedo",
            "secao": "contratos",
            "rotulo": "Contrato 0343/26 - anexo 1",
            "url_origem": "https://x/api (acao=contratos_frl/downloadAnexo)",
            "caminho_local": "evidencias/senadorcanedo/contratos/0343-26_anexo1.pdf",
            "sha256": "7b669bf28dad321a",
            "bytes": 450192,
            "content_type": "application/pdf",
        },
    )
    md = relatorio.gerar_relatorio_markdown(caso["id"], db=db)

    assert "[Contrato 0343/26 - anexo 1](evidencias/senadorcanedo/contratos/0343-26_anexo1.pdf)" in md
    # F6: a linha do achado traz o lastro (ev_id + sha256 curto) -- nunca so o link.
    assert "ev_000001 · sha256 `7b669bf28dad…`" in md
    # Indice de evidencias tambem lista o sha256 completo (mesma ancora de integridade).
    assert "| ev_000001 | pdf |" in md
    assert "`7b669bf28dad321a`" in md
    # Item tem lastro agora -- nao deveria aparecer como lacuna.
    assert "Contrato 0343/26 — Senador Canedo: nenhuma evidência" not in md


def test_relatorio_evidencia_com_item_id_vazio_migracao_leve(db: DB):
    """F6(c): evidencia antiga gravada com item_id='' (antes desta missao)
    continua aparecendo no indice -- so nao aparece amarrada a nenhum item
    especifico, e o item correspondente segue sem lastro (nao quebra caso
    existente, mas tambem nao inventa um vinculo que nao existe)."""
    caso = _caso_com_contrato(db)
    evidencia.registrar_evidencia(
        caso["id"],
        {
            "item_id": "",
            "tipo": "screenshot",
            "municipio": "senadorcanedo",
            "secao": "folha",
            "rotulo": "Folha antiga sem vinculo",
            "url_origem": "https://x",
            "caminho_local": "evidencias/senadorcanedo/folha/x.png",
            "sha256": "deadbeef",
            "bytes": 10,
            "content_type": "image/png",
        },
    )
    md = relatorio.gerar_relatorio_markdown(caso["id"], db=db)

    # continua no indice de evidencias.
    assert "| ev_000001 | screenshot |" in md
    assert "Folha antiga sem vinculo" in md
    # mas o item do caso segue sem lastro -- nunca inventa vinculo por coincidencia.
    assert "- Documentos: **[não verificado]** — nenhuma evidência coletada para este item." in md


def test_relatorio_quantificacao_folha_soma_liquido_por_mes(db: DB):
    caso = casos.criar_caso(
        titulo="Dano ao erário — folha",
        tipo="dano_erario_folha",
        alvos={"servidor": "Maria Silva"},
        municipios=["trindade"],
        db=db,
    )
    itens = [
        {"matricula": "12345", "nome": "Maria Silva", "ano": "2024", "mes": "03",
         "proventos": "R$ 3.500,00", "descontos": "R$ 500,00", "liquido": "R$ 3.000,00",
         "raw": {}},
        {"matricula": "12345", "nome": "Maria Silva", "ano": "2024", "mes": "06",
         "proventos": "R$ 3.700,00", "descontos": "R$ 500,00", "liquido": "R$ 3.200,00",
         "raw": {}},
    ]
    casos.adicionar_itens_da_busca(caso["id"], "trindade", "folha", itens, db=db)
    caso = casos.obter_caso(caso["id"], db=db)

    md = relatorio.gerar_relatorio_markdown(caso["id"], db=db)

    assert "### Folha — Maria Silva — mar/2024 — Trindade" in md
    assert "### Folha — Maria Silva — jun/2024 — Trindade" in md
    assert "Proventos R$ 3.500,00 · Descontos R$ 500,00 · Líquido R$ 3.000,00" in md
    assert "| Maria Silva | mar/2024 | R$ 3.000,00 |" in md
    assert "| Maria Silva | jun/2024 | R$ 3.200,00 |" in md
    assert "**Total** | | **R$ 6.200,00**" in md


def test_relatorio_folha_liquido_zero_nao_e_descartado_pelo_fallback(db: DB):
    """Líquido R$ 0,00 é dado real (ex.: folha totalmente consignada) -- o
    fallback para `item.valor` só deve entrar quando `raw.liquido` é
    realmente ausente (None), nunca porque 0.0 é falsy."""
    caso = casos.criar_caso(
        titulo="Servidor consignado",
        tipo="dano_erario_folha",
        alvos={"servidor": "João Souza"},
        municipios=["trindade"],
        db=db,
    )
    item = {
        "matricula": "99999",
        "nome": "João Souza",
        "ano": "2024",
        "mes": "05",
        "valor": "R$ 999,00",  # nunca deveria aparecer -- é so o fallback do item, nao o liquido real
        "liquido": "R$ 0,00",
        "raw": {},
    }
    casos.adicionar_itens_da_busca(caso["id"], "trindade", "folha", [item], db=db)
    caso = casos.obter_caso(caso["id"], db=db)

    md = relatorio.gerar_relatorio_markdown(caso["id"], db=db)

    assert "Líquido R$ 0,00" in md
    assert "| João Souza | mai/2024 | R$ 0,00 |" in md
    assert "R$ 999,00" not in md


def test_relatorio_folha_sem_evidencia_usa_rotulo_lastro(db: DB):
    """§6.3 usa 'Lastro' para folha (com ou sem evidência) -- 'Documentos' é
    exclusivo de contrato/dispensa/licitação."""
    caso = casos.criar_caso(
        titulo="Folha sem lastro",
        tipo="dano_erario_folha",
        alvos={"servidor": "Ana Paula"},
        municipios=["trindade"],
        db=db,
    )
    item = {"matricula": "111", "nome": "Ana Paula", "ano": "2024", "mes": "01",
            "liquido": "R$ 1.000,00", "raw": {}}
    casos.adicionar_itens_da_busca(caso["id"], "trindade", "folha", [item], db=db)
    caso = casos.obter_caso(caso["id"], db=db)

    md = relatorio.gerar_relatorio_markdown(caso["id"], db=db)

    assert "- Lastro: **[não verificado]** — nenhuma evidência coletada para este item." in md
    assert "- Documentos: **[não verificado]**" not in md


def test_salvar_relatorio_grava_em_disco(db: DB, tmp_path):
    caso = _caso_com_contrato(db)
    caminho = relatorio.salvar_relatorio(caso["id"], db=db)
    assert caminho.exists()
    assert caminho.name == "relatorio.md"
    assert caminho == relatorio.caminho_relatorio(caso["id"])
    conteudo = caminho.read_text(encoding="utf-8")
    assert conteudo.startswith("# Dossiê —")


def test_exportar_pdf_gera_arquivo_pdf_valido(db: DB):
    caso = _caso_com_contrato(db)
    caminho = relatorio.exportar_pdf(caso["id"], db=db)
    assert caminho.exists()
    assert caminho.name == "relatorio.pdf"
    assert caminho == relatorio.caminho_relatorio_pdf(caso["id"])
    assert caminho.read_bytes().startswith(b"%PDF-")


def test_exportar_pdf_sobrescreve_arquivo_existente(db: DB):
    caso = _caso_com_contrato(db)
    caminho = relatorio.exportar_pdf(caso["id"], db=db)
    tamanho_1 = caminho.stat().st_size
    caminho_2 = relatorio.exportar_pdf(caso["id"], db=db)
    assert caminho_2 == caminho
    assert caminho.stat().st_size == tamanho_1


# --------------------------------------------------------------------------- #
# W1-F1/F2 (revisao-w1.md): marcadores inline resolvidos + sha256 integro no PDF
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("linha", "esperado"),
    [
        ("Foram encontrados **23** item(ns) neste caso", "Foram encontrados 23 item(ns) neste caso"),
        (
            "- Documentos: **[não verificado]** — nenhuma evidência coletada.",
            "- Documentos: [não verificado] — nenhuma evidência coletada.",
        ),
        (
            "- Documentos: [Contrato 016.pdf](evidencias/x/016.pdf) · ev_000001 · sha256 `abc123`",
            "- Documentos: Contrato 016.pdf (evidencias/x/016.pdf) · ev_000001 · sha256 abc123",
        ),
        (
            "_Alguns valores não puderam ser lidos — marcados **[não verificado]**._",
            "Alguns valores não puderam ser lidos — marcados [não verificado].",
        ),
    ],
)
def test_resolver_inline_pdf_remove_marcadores_preserva_texto(linha: str, esperado: str):
    assert relatorio._resolver_inline_pdf(linha) == esperado


def test_exportar_pdf_resolve_marcadores_inline_e_mantem_sha256_integro(db: DB):
    """W1-F1: negrito/link/codigo inline nao devem sobrar como asteriscos,
    colchetes ou crases no texto do PDF gerado. W1-F2: o sha256 completo
    (64 chars) da linha de tabela do indice de evidencias tem que sair
    inteiro, sem espaco inserido no meio pelo quebrador de tokens longos."""
    caso = _caso_com_contrato(db)
    item_id = caso["itens"][0]["id"]
    sha_completo = "b6b272c3cd1182ca89b117d1b921feb8e0b4f9cada2d6a0c177a0e88bf4a1098"
    evidencia.registrar_evidencia(
        caso["id"],
        {
            "item_id": item_id,
            "tipo": "pdf",
            "municipio": "senadorcanedo",
            "secao": "contratos",
            "rotulo": "Contrato 0343/26 - anexo 1",
            "url_origem": "https://x/api",
            "caminho_local": "evidencias/senadorcanedo/contratos/anexo1.pdf",
            "sha256": sha_completo,
            "bytes": 450192,
            "content_type": "application/pdf",
        },
    )

    caminho = relatorio.exportar_pdf(caso["id"], db=db)
    reader = PdfReader(str(caminho))
    texto = "\n".join(pagina.extract_text() for pagina in reader.pages)

    assert "**" not in texto
    assert "`" not in texto
    # unico item do caso tem evidencia -- sem lacuna "[não verificado]", entao
    # nao deve sobrar nenhum colchete de link markdown (`[texto](url)`) cru.
    assert "[" not in texto and "](" not in texto
    # sha256 integro: junta as linhas (extract_text quebra em '\n' por causa
    # da largura da pagina) e confere que a sequencia de 64 chars aparece
    # sem espaco no meio.
    assert sha_completo in texto.replace("\n", "")


# --------------------------------------------------------------------------- #
# resolver_arquivo_evidencia -- serve arquivo com validacao de path
# --------------------------------------------------------------------------- #


def test_resolver_arquivo_evidencia_encontra_arquivo_real(db: DB, tmp_path):
    caso = _caso_com_contrato(db)
    pasta = evidencia.caminho_caso(caso["id"]) / "evidencias" / "senadorcanedo" / "contratos"
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / "0343-26_anexo1.pdf"
    arquivo.write_bytes(b"%PDF-1.7 conteudo fake")
    evidencia.registrar_evidencia(
        caso["id"],
        {
            "item_id": caso["itens"][0]["id"],
            "tipo": "pdf",
            "municipio": "senadorcanedo",
            "secao": "contratos",
            "rotulo": "Contrato 0343/26 - anexo 1",
            "url_origem": "https://x/api",
            "caminho_local": "evidencias/senadorcanedo/contratos/0343-26_anexo1.pdf",
            "sha256": "abc123",
            "bytes": arquivo.stat().st_size,
            "content_type": "application/pdf",
        },
    )
    resultado = relatorio.resolver_arquivo_evidencia(caso["id"], "ev_000001")
    assert resultado is not None
    caminho, content_type, nome = resultado
    assert caminho == arquivo.resolve()
    assert content_type == "application/pdf"
    assert nome == "0343-26_anexo1.pdf"


def test_resolver_arquivo_evidencia_inexistente_retorna_none(db: DB):
    caso = _caso_com_contrato(db)
    assert relatorio.resolver_arquivo_evidencia(caso["id"], "ev_999999") is None


def test_resolver_arquivo_evidencia_recusa_path_traversal(db: DB, tmp_path):
    caso = _caso_com_contrato(db)
    # Um manifesto malicioso/corrompido tentando escapar da pasta do caso --
    # nunca deveria acontecer via `registrar_evidencia`, mas o resolvedor
    # recusa mesmo assim (defesa em profundidade).
    evidencia.registrar_evidencia(
        caso["id"],
        {
            "item_id": caso["itens"][0]["id"],
            "tipo": "pdf",
            "municipio": "senadorcanedo",
            "secao": "contratos",
            "rotulo": "tentativa maliciosa",
            "url_origem": "https://x",
            "caminho_local": "../../../etc/passwd",
            "sha256": "xxx",
            "bytes": 1,
            "content_type": "application/pdf",
        },
    )
    with pytest.raises(relatorio.CaminhoEvidenciaInvalido):
        relatorio.resolver_arquivo_evidencia(caso["id"], "ev_000001")
