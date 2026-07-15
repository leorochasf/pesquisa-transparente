"""Testes da camada de evidencia: manifesto (sem rede) + download de PDFs (mockado).

O download de PDF real contra o portal (Senador Canedo, dispensa/contrato) e
verificado RODANDO fora do pytest (nao ha rede aqui — mesmo padrao de
`test_anexos.py`: httpx.MockTransport reproduz os formatos reais observados
ao vivo).
"""

from __future__ import annotations

import base64
import json
from urllib.parse import parse_qs

import httpx
import pytest

from busca_go.db import DB
from busca_go.nucleo import anexos, casos, evidencia

_PDF = b"%PDF-1.7\n%fake pdf body\n%%EOF\n"
_PDF_B64 = base64.b64encode(_PDF).decode("ascii")

_SC_ANEXOS = [
    {"chave": "26000000000019324", "numero_contrato": "0343/26", "nome": "CONTRATO - PNCP",
     "id": "26000000000019324"},
    {"chave": "26000000000019325", "nome": "EXTRATO CONTRATO - PNCP", "id": "26000000000019325"},
]


def make_portal(*, sc_anexos=None, falha_no_segundo=False, contador_downloads=None):
    sc = _SC_ANEXOS if sc_anexos is None else sc_anexos

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api"
        form = parse_qs(request.content.decode())
        blk = json.loads(form["params"][0])["k1"]
        acao = blk["acao"]
        if acao == "licitacoes_frl/listarAnexos":
            return httpx.Response(200, json={"k1": {"total": len(sc), "dados": sc}})
        if acao == "licitacoes_frl/listarAditivos":
            return httpx.Response(200, json={"k1": {"total": 0, "dados": []}})
        if acao == "licitacoes_frl/downloadAnexo":
            if contador_downloads is not None:
                contador_downloads.append(1)
            item = blk.get("item") if isinstance(blk.get("item"), dict) else blk
            if falha_no_segundo and item.get("id") == "26000000000019325":
                return httpx.Response(200, json={"k1": {"erro": "sem arquivo"}})
            return httpx.Response(200, json={"k1": {"anexo": _PDF_B64}})
        return httpx.Response(200, json=[])

    return httpx.MockTransport(handler)


def _client(transport):
    return httpx.AsyncClient(transport=transport, base_url="https://x")


# --------------------------------------------------------------------------- #
# Manifesto (sem rede)
# --------------------------------------------------------------------------- #


def test_manifesto_escrita_e_leitura_sem_rede(tmp_path, monkeypatch):
    monkeypatch.setattr(evidencia.settings, "DATA_DIR", tmp_path)
    caso_id = "caso_teste"
    assert evidencia.ler_manifesto(caso_id) == []

    e1 = evidencia.registrar_evidencia(
        caso_id,
        {"tipo": "pdf", "municipio": "senadorcanedo", "secao": "contratos",
         "rotulo": "Contrato 1", "url_origem": "https://x/api", "caminho_local": "a.pdf",
         "sha256": "abc", "bytes": 10, "content_type": "application/pdf"},
    )
    e2 = evidencia.registrar_evidencia(
        caso_id,
        {"tipo": "screenshot", "municipio": "senadorcanedo", "secao": "folha",
         "rotulo": "Folha X", "url_origem": "https://x", "caminho_local": "b.png",
         "sha256": "def", "bytes": 20, "content_type": "image/png"},
    )
    assert e1["evidencia_id"] == "ev_000001"
    assert e2["evidencia_id"] == "ev_000002"
    assert e1["caso_id"] == caso_id
    assert "coletado_em" in e1

    lidas = evidencia.ler_manifesto(caso_id)
    assert len(lidas) == 2
    assert lidas[0]["caminho_local"] == "a.pdf"
    assert lidas[1]["tipo"] == "screenshot"
    # append-only: o arquivo tem exatamente 2 linhas JSON.
    conteudo = evidencia._manifesto_path(caso_id).read_text(encoding="utf-8").splitlines()
    assert len(conteudo) == 2
    for linha in conteudo:
        json.loads(linha)  # cada linha e um JSON valido isolado


def test_contar_pdfs_manifesto(tmp_path, monkeypatch):
    monkeypatch.setattr(evidencia.settings, "DATA_DIR", tmp_path)
    caso_id = "caso_teste"
    evidencia.registrar_evidencia(caso_id, {"tipo": "pdf", "caminho_local": "a.pdf"})
    evidencia.registrar_evidencia(caso_id, {"tipo": "screenshot", "caminho_local": "b.png"})
    evidencia.registrar_evidencia(caso_id, {"tipo": "pdf", "caminho_local": "c.pdf"})
    assert evidencia.contar_pdfs_manifesto(caso_id) == 2


def test_pendentes_escrita_e_leitura_sem_rede(tmp_path, monkeypatch):
    monkeypatch.setattr(evidencia.settings, "DATA_DIR", tmp_path)
    caso_id = "caso_teste"
    assert evidencia.ler_pendentes(caso_id) == []
    evidencia._registrar_pendentes(
        caso_id, [{"municipio": "senadorcanedo", "secao": "contratos", "rotulo": "x", "ref": "tok"}]
    )
    pend = evidencia.ler_pendentes(caso_id)
    assert len(pend) == 1
    assert pend[0]["ref"] == "tok"
    assert "registrado_em" in pend[0]


# --------------------------------------------------------------------------- #
# Indexacao na tabela `evidencias` (W2-F1) -- ver AUDITORIA/frontend-caso/revisao-w2.md
# --------------------------------------------------------------------------- #


def test_registrar_evidencia_indexa_na_tabela_evidencias_quando_db_informado(tmp_path, monkeypatch):
    """W2-F1(i): com `db`, registrar_evidencia TAMBEM insere na tabela
    `evidencias` -- o manifesto continua a fonte de auditoria, mas e a tabela
    que `casos.obter_caso` le para devolver `caso.evidencias` na API."""
    monkeypatch.setattr(evidencia.settings, "DATA_DIR", tmp_path)
    db = DB(db_path=tmp_path / "casos-teste.db")
    caso = casos.criar_caso(
        titulo="Caso com evidencia indexada", tipo="livre", alvos={}, municipios=["trindade"], db=db,
    )
    caso_id = caso["id"]
    entrada = evidencia.registrar_evidencia(
        caso_id,
        {"tipo": "pdf", "municipio": "trindade", "secao": "contratos", "rotulo": "x",
         "url_origem": "https://x", "caminho_local": "a.pdf", "sha256": "abc123",
         "bytes": 10, "content_type": "application/pdf"},
        db=db,
    )
    with db._lock, db.connect() as conn:
        row = conn.execute("SELECT * FROM evidencias WHERE id = ?", (entrada["evidencia_id"],)).fetchone()
    assert row is not None
    assert row["caso_id"] == caso_id
    assert row["item_id"] is None  # sem item_id na entrada -- "" vira NULL, nao string vazia
    assert row["sha256"] == "abc123"
    assert row["content_type"] == "application/pdf"


def test_registrar_evidencia_sem_db_nao_toca_a_tabela(tmp_path, monkeypatch):
    """Sem `db` (uso direto/teste sem caso persistido), so o manifesto e
    gravado -- nunca tenta indexar (evitaria FK falhar contra um caso_id que
    nao existe em `casos`)."""
    monkeypatch.setattr(evidencia.settings, "DATA_DIR", tmp_path)
    db = DB(db_path=tmp_path / "casos-teste.db")
    evidencia.registrar_evidencia(
        "caso_sem_db", {"tipo": "pdf", "caminho_local": "a.pdf", "sha256": "x",
                        "url_origem": "https://x", "content_type": "application/pdf", "bytes": 1},
    )
    with db._lock, db.connect() as conn:
        total = conn.execute("SELECT COUNT(*) AS n FROM evidencias").fetchone()["n"]
    assert total == 0


def test_backfill_evidencias_idempotente_a_partir_do_manifesto(tmp_path, monkeypatch):
    """W2-F1(ii): backfill varre manifesto.jsonl de evidencia coletada ANTES
    da correcao (so manifesto, sem `db`) e indexa na tabela; rodar 2x nao
    duplica (INSERT OR IGNORE por id)."""
    monkeypatch.setattr(evidencia.settings, "DATA_DIR", tmp_path)
    db = DB(db_path=tmp_path / "casos-teste.db")
    caso = casos.criar_caso(
        titulo="Caso pre-existente", tipo="livre", alvos={}, municipios=["trindade"], db=db,
    )
    caso_id = caso["id"]
    # simula 2 evidencias coletadas ANTES da correcao (so manifesto, sem db).
    evidencia.registrar_evidencia(
        caso_id,
        {"tipo": "pdf", "municipio": "trindade", "secao": "contratos", "rotulo": "x",
         "url_origem": "https://x", "caminho_local": "a.pdf", "sha256": "abc",
         "bytes": 10, "content_type": "application/pdf"},
    )
    evidencia.registrar_evidencia(
        caso_id,
        {"tipo": "screenshot", "municipio": "trindade", "secao": "folha", "rotulo": "y",
         "url_origem": "https://x", "caminho_local": "b.png", "sha256": "def",
         "bytes": 20, "content_type": "image/png"},
    )
    with db._lock, db.connect() as conn:
        antes = conn.execute("SELECT COUNT(*) AS n FROM evidencias").fetchone()["n"]
    assert antes == 0  # nada indexado ainda -- so manifesto

    inseridas1 = evidencia.backfill_evidencias(db=db)
    assert inseridas1 == 2
    with db._lock, db.connect() as conn:
        total1 = conn.execute("SELECT COUNT(*) AS n FROM evidencias WHERE caso_id = ?", (caso_id,)).fetchone()["n"]
    assert total1 == 2

    inseridas2 = evidencia.backfill_evidencias(db=db)
    assert inseridas2 == 0  # idempotente: reexecutar nao encontra nada novo
    with db._lock, db.connect() as conn:
        total2 = conn.execute("SELECT COUNT(*) AS n FROM evidencias").fetchone()["n"]
    assert total2 == 2  # nao duplicou


def test_obter_caso_devolve_evidencias_com_item_id_vinculado(tmp_path, monkeypatch):
    """W2-F1(iii): `casos.obter_caso` (o que `GET /api/casos/{id}` devolve)
    passa a trazer `evidencias` NAO-vazio com `item_id` vinculado -- a raiz do
    finding W2-F1 (dossie mostraria "[nao verificado]" mesmo com prova
    coletada, ver revisao-w2.md)."""
    monkeypatch.setattr(evidencia.settings, "DATA_DIR", tmp_path)
    db = DB(db_path=tmp_path / "casos-teste.db")
    caso = casos.criar_caso(
        titulo="Caso com item e evidencia", tipo="livre", alvos={}, municipios=["trindade"], db=db,
    )
    caso_id = caso["id"]
    item_id = casos.adicionar_item(
        caso_id, "trindade", "contratos",
        {"titulo": "0001/26", "ref_registro": {"id": "1", "numero": "1", "ano": "2026"}, "raw": {}},
        db=db,
    )
    evidencia.registrar_evidencia(
        caso_id,
        {"item_id": item_id, "tipo": "pdf", "municipio": "trindade", "secao": "contratos",
         "rotulo": "x", "url_origem": "https://x", "caminho_local": "a.pdf", "sha256": "abc",
         "bytes": 10, "content_type": "application/pdf"},
        db=db,
    )
    caso_obtido = casos.obter_caso(caso_id, db=db)
    assert len(caso_obtido["evidencias"]) == 1
    assert caso_obtido["evidencias"][0]["item_id"] == item_id
    assert caso_obtido["evidencias"][0]["sha256"] == "abc"


# --------------------------------------------------------------------------- #
# Download de PDFs de um registro (mockado, sem rede real)
# --------------------------------------------------------------------------- #


async def test_baixa_todos_os_anexos_e_registra_manifesto(tmp_path, monkeypatch):
    monkeypatch.setattr(evidencia.settings, "DATA_DIR", tmp_path)
    caso_id = "caso_dispensa_sc"
    registro = {"id": "26000000000001413", "numero": "0343/26", "ano": "2026"}
    async with _client(make_portal()) as cli:
        resultado = await evidencia.baixar_evidencias_registro(
            caso_id, "senadorcanedo", "dispensas", registro, item_id="it_001", client=cli
        )
    assert len(resultado.baixados) == 2
    assert resultado.falhas == []
    assert resultado.pendentes == []
    assert resultado.teto_atingido is False

    manifesto = evidencia.ler_manifesto(caso_id)
    assert len(manifesto) == 2
    for entrada in manifesto:
        assert entrada["item_id"] == "it_001"
        assert entrada["tipo"] == "pdf"
        assert entrada["municipio"] == "senadorcanedo"
        caminho = evidencia.caminho_caso(caso_id) / entrada["caminho_local"]
        assert caminho.exists()
        blob = caminho.read_bytes()
        # reabre o PDF, recalcula o sha256 e confere que bate (criterio de pronto)
        import hashlib
        assert hashlib.sha256(blob).hexdigest() == entrada["sha256"]
        assert blob[:5] == b"%PDF-"


async def test_registro_sem_anexo_nao_grava_nada(tmp_path, monkeypatch):
    monkeypatch.setattr(evidencia.settings, "DATA_DIR", tmp_path)
    caso_id = "caso_vazio"
    async with _client(make_portal(sc_anexos=[])) as cli:
        resultado = await evidencia.baixar_evidencias_registro(
            caso_id, "senadorcanedo", "dispensas", {"id": "1", "numero": "1", "ano": "2026"}, client=cli
        )
    assert resultado.baixados == []
    assert evidencia.ler_manifesto(caso_id) == []


async def test_registro_sem_numero_levanta_registroincompleto(tmp_path, monkeypatch):
    """F2: registro empobrecido (so 'id') numa secao com anexo nunca vira
    silencio (baixados:[], falhas:[]) -- levanta erro estruturado dizendo o
    que falta, ANTES de bater na rede (caso real da aceitacao final:
    `{'id':'517'}` devolveu 0 anexos sem avisar; com 'numero' baixou 1)."""
    monkeypatch.setattr(evidencia.settings, "DATA_DIR", tmp_path)
    caso_id = "caso_f2_incompleto"
    with pytest.raises(evidencia.RegistroIncompleto) as exc_info:
        await evidencia.baixar_evidencias_registro(caso_id, "senadorcanedo", "dispensas", {"id": "517"})
    assert exc_info.value.faltando == ["numero"]
    assert "numero" in str(exc_info.value)
    # nunca bateu na rede nem gravou nada -- falhou antes disso.
    assert evidencia.ler_manifesto(caso_id) == []


async def test_registro_com_numero_sem_ano_nao_levanta_erro(tmp_path, monkeypatch):
    """'ano' e enviado quando presente mas nao e exigido — mesmo criterio que
    `agente/tools.py` (ACEIT-F1) ja valida antes de chamar esta camada."""
    monkeypatch.setattr(evidencia.settings, "DATA_DIR", tmp_path)
    caso_id = "caso_f2_so_numero"
    async with _client(make_portal()) as cli:
        resultado = await evidencia.baixar_evidencias_registro(
            caso_id, "senadorcanedo", "dispensas", {"id": "26000000000001413", "numero": "0343/26"}, client=cli
        )
    assert len(resultado.baixados) == 2


async def test_falha_em_um_anexo_nao_derruba_os_demais(tmp_path, monkeypatch):
    monkeypatch.setattr(evidencia.settings, "DATA_DIR", tmp_path)
    caso_id = "caso_falha_parcial"
    registro = {"id": "26000000000001413", "numero": "0343/26", "ano": "2026"}
    async with _client(make_portal(falha_no_segundo=True)) as cli:
        resultado = await evidencia.baixar_evidencias_registro(
            caso_id, "senadorcanedo", "dispensas", registro, client=cli
        )
    assert len(resultado.baixados) == 1
    assert len(resultado.falhas) == 1
    assert evidencia.contar_pdfs_manifesto(caso_id) == 1


async def test_teto_de_pdfs_registra_pendentes_e_para(tmp_path, monkeypatch):
    monkeypatch.setattr(evidencia.settings, "DATA_DIR", tmp_path)
    monkeypatch.setattr(evidencia, "TETO_PDFS_CASO", 1)
    caso_id = "caso_teto"
    registro = {"id": "26000000000001413", "numero": "0343/26", "ano": "2026"}
    async with _client(make_portal()) as cli:
        resultado = await evidencia.baixar_evidencias_registro(
            caso_id, "senadorcanedo", "dispensas", registro, client=cli
        )
    assert len(resultado.baixados) == 1
    assert len(resultado.pendentes) == 1
    assert resultado.teto_atingido is True
    assert evidencia.contar_pdfs_manifesto(caso_id) == 1
    pend = evidencia.ler_pendentes(caso_id)
    assert len(pend) == 1
    assert pend[0]["rotulo"] == "EXTRATO CONTRATO - PNCP"


async def test_idempotente_nao_duplica_manifesto_em_segunda_chamada(tmp_path, monkeypatch):
    monkeypatch.setattr(evidencia.settings, "DATA_DIR", tmp_path)
    caso_id = "caso_repeticao"
    registro = {"id": "26000000000001413", "numero": "0343/26", "ano": "2026"}
    async with _client(make_portal()) as cli:
        r1 = await evidencia.baixar_evidencias_registro(
            caso_id, "senadorcanedo", "dispensas", registro, client=cli
        )
        r2 = await evidencia.baixar_evidencias_registro(
            caso_id, "senadorcanedo", "dispensas", registro, client=cli
        )
    assert len(r1.baixados) == 2
    assert len(r2.baixados) == 2
    # segunda chamada nao duplica: manifesto continua com 2 entradas.
    assert len(evidencia.ler_manifesto(caso_id)) == 2


async def test_idempotencia_checada_antes_do_teto(tmp_path, monkeypatch):
    """F1: reexecutar um registro ja completo (mesmo caso no teto) NAO gera pendente falso."""
    monkeypatch.setattr(evidencia.settings, "DATA_DIR", tmp_path)
    monkeypatch.setattr(evidencia, "TETO_PDFS_CASO", 2)
    caso_id = "caso_f1"
    registro = {"id": "26000000000001413", "numero": "0343/26", "ano": "2026"}
    async with _client(make_portal()) as cli:
        r1 = await evidencia.baixar_evidencias_registro(caso_id, "senadorcanedo", "dispensas", registro, client=cli)
        assert len(r1.baixados) == 2 and r1.pendentes == []
        # teto (2) ja esta todo consumido por ESTE registro; reexecutar nao
        # pode reclassificar os 2 anexos ja baixados como pendentes.
        r2 = await evidencia.baixar_evidencias_registro(caso_id, "senadorcanedo", "dispensas", registro, client=cli)
    assert len(r2.baixados) == 2
    assert r2.pendentes == []
    assert r2.teto_atingido is False
    assert evidencia.ler_pendentes(caso_id) == []


async def test_reexecucao_nao_rebaixa_da_rede_arquivo_ja_em_disco(tmp_path, monkeypatch):
    """F4: reexecutar um registro ja baixado nao bate downloadAnexo de novo (so listarAnexos)."""
    monkeypatch.setattr(evidencia.settings, "DATA_DIR", tmp_path)
    caso_id = "caso_f4"
    registro = {"id": "26000000000001413", "numero": "0343/26", "ano": "2026"}
    contador = []
    async with _client(make_portal(contador_downloads=contador)) as cli:
        await evidencia.baixar_evidencias_registro(caso_id, "senadorcanedo", "dispensas", registro, client=cli)
        assert len(contador) == 2
        r2 = await evidencia.baixar_evidencias_registro(caso_id, "senadorcanedo", "dispensas", registro, client=cli)
    assert len(r2.baixados) == 2
    # nenhuma chamada NOVA de downloadAnexo na segunda execucao.
    assert len(contador) == 2


async def test_pendentes_nao_duplicam_entre_execucoes(tmp_path, monkeypatch):
    """F2: reexecutar um registro que segue estourando o teto nao duplica o indice de pendentes."""
    monkeypatch.setattr(evidencia.settings, "DATA_DIR", tmp_path)
    monkeypatch.setattr(evidencia, "TETO_PDFS_CASO", 1)
    caso_id = "caso_f2"
    registro = {"id": "26000000000001413", "numero": "0343/26", "ano": "2026"}
    async with _client(make_portal()) as cli:
        await evidencia.baixar_evidencias_registro(caso_id, "senadorcanedo", "dispensas", registro, client=cli)
        await evidencia.baixar_evidencias_registro(caso_id, "senadorcanedo", "dispensas", registro, client=cli)
        await evidencia.baixar_evidencias_registro(caso_id, "senadorcanedo", "dispensas", registro, client=cli)
    pend = evidencia.ler_pendentes(caso_id)
    assert len(pend) == 1  # nao 3


def test_manifesto_tolera_linha_corrompida_sem_derrubar_o_caso(tmp_path, monkeypatch):
    """F3: crash no meio de um append nao inutiliza o manifesto inteiro."""
    monkeypatch.setattr(evidencia.settings, "DATA_DIR", tmp_path)
    caso_id = "caso_f3"
    evidencia.registrar_evidencia(caso_id, {"tipo": "pdf", "caminho_local": "a.pdf"})
    evidencia.registrar_evidencia(caso_id, {"tipo": "pdf", "caminho_local": "b.pdf"})
    # simula escrita truncada (kill no meio do f.write da 3a linha).
    with evidencia._manifesto_path(caso_id).open("a", encoding="utf-8") as f:
        f.write('{"evidencia_id":"ev_000003","tipo":"pdf","caminho_local":"c.pdf"')  # sem fechar
    lidas = evidencia.ler_manifesto(caso_id)  # nao lanca
    assert len(lidas) == 2
    assert {e["caminho_local"] for e in lidas} == {"a.pdf", "b.pdf"}
    # a leitura corrompida nao contamina contagens dependentes (teto, dedup).
    assert evidencia.contar_pdfs_manifesto(caso_id) == 2


def test_registrar_evidencia_nao_deixa_chamador_sobrescrever_identificadores(tmp_path, monkeypatch):
    """F11: evidencia_id/caso_id/coletado_em sao SEMPRE gerados, nunca vem do chamador."""
    monkeypatch.setattr(evidencia.settings, "DATA_DIR", tmp_path)
    caso_id = "caso_real"
    entrada = evidencia.registrar_evidencia(
        caso_id,
        {"evidencia_id": "ev_forjado", "caso_id": "caso_forjado", "tipo": "pdf", "caminho_local": "a.pdf"},
    )
    assert entrada["evidencia_id"] == "ev_000001"
    assert entrada["caso_id"] == caso_id


# --------------------------------------------------------------------------- #
# Screenshot de folha: filtro por matricula (mockado, sem rede/browser)
# --------------------------------------------------------------------------- #


def _item_folha(nome, matricula):
    return {"matricula": matricula, "nome": nome, "cargo": "X", "lotacao": "Y", "orgao": "Z",
            "vinculo": "", "referencia": "Marco/2026", "tipo_folha": "Folha Mensal", "ano": "2026",
            "mes": "03", "proventos": "1,00", "descontos": "0,00", "liquido": "1,00",
            "cpf_mascarado": "xxx.xxx.xxx-xx", "raw": {}}


async def test_matricula_sem_match_levanta_evidenciaambigua_com_candidatos(monkeypatch):
    """PRIORIDADE 1 (F5): matricula sem match NUNCA cai para os homonimos em silencio."""

    async def fake_grupo_folha(client, mun, tipo, needle, ano, mes):
        itens = [_item_folha("MARIA DA SILVA", "111"), _item_folha("MARIA DOS SANTOS", "222")]
        return {"secao": "folha", "itens": itens, "servidores": []}, []

    monkeypatch.setattr(evidencia.entidade, "_grupo_folha", fake_grupo_folha)
    with pytest.raises(evidencia.EvidenciaAmbigua) as exc_info:
        await evidencia.capturar_screenshot_folha("caso_x", "senadorcanedo", "MARIA", 2026, 3, matricula="999")
    msg = str(exc_info.value)
    # lista os candidatos reais (nome + matricula) para o chamador decidir.
    assert "MARIA DA SILVA" in msg and "111" in msg
    assert "MARIA DOS SANTOS" in msg and "222" in msg
    assert "999" in msg


async def test_matricula_com_match_nao_levanta_erro(monkeypatch):
    async def fake_grupo_folha(client, mun, tipo, needle, ano, mes):
        itens = [_item_folha("MARIA DA SILVA", "111"), _item_folha("MARIA DOS SANTOS", "222")]
        return {"secao": "folha", "itens": itens, "servidores": []}, []

    monkeypatch.setattr(evidencia.entidade, "_grupo_folha", fake_grupo_folha)

    # a excecao so deve vir do filtro de matricula: forcamos a falhar ANTES de
    # tocar Playwright para confirmar que o match ocorreu (nao caiu no branch
    # de erro) sem precisar de um browser real neste teste.
    class _BrowserTocado(Exception):
        pass

    class _FakeNucleoClient:
        _context = object()

        async def _new_page(self):
            raise _BrowserTocado("chegou ate o browser com matricula casando")

    with pytest.raises(_BrowserTocado):
        await evidencia.capturar_screenshot_folha(
            "caso_x", "senadorcanedo", "MARIA", 2026, 3, matricula="111",
            nucleo_client=_FakeNucleoClient(),
        )


# --------------------------------------------------------------------------- #
# Fluxo manual de folha num passo so (F5/F6): persistir_e_capturar_folha
# --------------------------------------------------------------------------- #


async def test_persistir_e_capturar_folha_persiste_item_e_vincula_evidencia(tmp_path, monkeypatch):
    """F5: 1 chamada persiste o item E captura a evidencia com o MESMO
    item_id -- sem 2 acoes separadas nem item_id='' desconectado (F6)."""
    monkeypatch.setattr(evidencia.settings, "DATA_DIR", tmp_path)
    db = DB(db_path=tmp_path / "casos-teste.db")
    caso = casos.criar_caso(
        titulo="Dano ao erario -- folha", tipo="dano_erario_folha",
        alvos={"servidor": "Joana"}, municipios=["senadorcanedo"], db=db,
    )

    async def fake_grupo_folha(client, mun, tipo, needle, ano, mes):
        itens = [_item_folha("JOANA TESTE DA SILVA", "90001")]
        return {"secao": "folha", "itens": itens, "servidores": []}, ["aviso da busca"]

    monkeypatch.setattr(evidencia.entidade, "_grupo_folha", fake_grupo_folha)

    capturado: dict = {}

    async def fake_captura(caso_id, slug, nome, ano, mes, matricula=None, item_id=None, nucleo_client=None, http_client=None, db=None):
        capturado["item_id"] = item_id
        capturado["matricula"] = matricula
        return evidencia.EvidenciaFolha(
            png={"evidencia_id": "ev_000001", "item_id": item_id},
            json_valores={"itens": []},
            avisos=["aviso da captura"],
            json_entrada={"evidencia_id": "ev_000002", "item_id": item_id},
        )

    monkeypatch.setattr(evidencia, "capturar_screenshot_folha", fake_captura)

    resultado = await evidencia.persistir_e_capturar_folha(
        caso["id"], "senadorcanedo", "JOANA", 2025, 1, db=db,
    )

    assert resultado["item_id"]
    # o item_id repassado a captura e EXATAMENTE o item_id persistido -- o
    # elo item<->evidencia (F6) nasce ja vinculado, nunca item_id=''.
    assert capturado["item_id"] == resultado["item_id"]
    assert capturado["matricula"] == "90001"  # resolvida sozinha (sem matricula informada)
    assert resultado["evidencia_png_id"] == "ev_000001"
    assert resultado["evidencia_json_id"] == "ev_000002"
    assert "aviso da busca" in resultado["avisos"] and "aviso da captura" in resultado["avisos"]

    item = casos.obter_item(resultado["item_id"], db=db)
    assert item is not None
    assert item["municipio"] == "senadorcanedo" and item["secao"] == "folha"
    assert item["documento"] == "90001"  # matricula


async def test_persistir_e_capturar_folha_sem_registro_levanta_indisponivel(tmp_path, monkeypatch):
    monkeypatch.setattr(evidencia.settings, "DATA_DIR", tmp_path)
    db = DB(db_path=tmp_path / "casos-teste.db")
    caso = casos.criar_caso(
        titulo="Sem registro", tipo="dano_erario_folha", alvos={}, municipios=["senadorcanedo"], db=db,
    )

    async def fake_grupo_folha(client, mun, tipo, needle, ano, mes):
        return {"secao": "folha", "itens": [], "servidores": []}, []

    monkeypatch.setattr(evidencia.entidade, "_grupo_folha", fake_grupo_folha)
    with pytest.raises(evidencia.EvidenciaIndisponivel):
        await evidencia.persistir_e_capturar_folha(caso["id"], "senadorcanedo", "NINGUEM", 2025, 1, db=db)


async def test_persistir_e_capturar_folha_homonimo_sem_matricula_levanta_ambigua(tmp_path, monkeypatch):
    """F5: sem matricula, 2 servidores distintos para o mesmo nome nunca
    escolhe por engano -- levanta EvidenciaAmbigua com os candidatos, e nao
    persiste nem captura nada."""
    monkeypatch.setattr(evidencia.settings, "DATA_DIR", tmp_path)
    db = DB(db_path=tmp_path / "casos-teste.db")
    caso = casos.criar_caso(
        titulo="Homonimo", tipo="dano_erario_folha", alvos={}, municipios=["senadorcanedo"], db=db,
    )

    async def fake_grupo_folha(client, mun, tipo, needle, ano, mes):
        itens = [_item_folha("MARIA DA SILVA", "111"), _item_folha("MARIA DOS SANTOS", "222")]
        return {"secao": "folha", "itens": itens, "servidores": []}, []

    monkeypatch.setattr(evidencia.entidade, "_grupo_folha", fake_grupo_folha)
    with pytest.raises(evidencia.EvidenciaAmbigua) as exc_info:
        await evidencia.persistir_e_capturar_folha(caso["id"], "senadorcanedo", "MARIA", 2025, 1, db=db)
    msg = str(exc_info.value)
    assert "MARIA DA SILVA" in msg and "111" in msg
    assert "MARIA DOS SANTOS" in msg and "222" in msg
    caso_apos = casos.obter_caso(caso["id"], db=db)
    assert caso_apos["itens"] == []  # nada persistido -- nunca escolhe por engano


def test_descrever_origem_nao_expoe_base64_nem_assinatura():
    from busca_go.municipios import get as get_mun

    mun = get_mun("senadorcanedo")
    ref = anexos._encode_ref({"m": "A", "acao": "licitacoes_frl/downloadAnexo", "item": {"id": "1"}})
    desc = evidencia._descrever_origem(mun, "dispensas", ref)
    assert "base64" not in desc.lower()
    assert ref not in desc
    assert "acao=licitacoes_frl/downloadAnexo" in desc


def test_slug_numero_saneia():
    assert evidencia._slug_numero("0343/26") == "0343-26"
    assert evidencia._slug_numero("") == "registro"
    assert evidencia._slug_numero("a b/c") == "a-b-c"
