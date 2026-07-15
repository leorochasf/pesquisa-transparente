"""Testes da cabeca (`busca_go/agente/cabeca.py`): planejamento, validacao
DETERMINISTICA contra o manifesto (guardrail §6.2 #3/#5), reexecucao ->
lacuna, e o fluxo `investigar()` fim a fim com OpenRouter mockado (sem rede)."""

from __future__ import annotations

import json

import pytest

from busca_go.agente import cabeca
from busca_go.agente import log as log_module
from busca_go.agente.openrouter import CustoAcumulado
from busca_go.agente.worker import ResultadoSubtarefa
from busca_go.db import DB
from busca_go.nucleo import casos as casos_module
from busca_go.nucleo import evidencia


@pytest.fixture
def caso_db(tmp_path, monkeypatch: pytest.MonkeyPatch) -> DB:
    banco = DB(db_path=tmp_path / "casos-teste.db")
    monkeypatch.setattr(casos_module, "default_db", lambda: banco)
    monkeypatch.setattr(evidencia.settings, "DATA_DIR", tmp_path)
    return banco


def _caso(banco: DB, **kwargs) -> str:
    padrao = dict(
        titulo="Escritorio X — dispensa",
        tipo="dispensa_advocacia",
        alvos={"cnpj": "02292266000180"},
        municipios=["trindade"],
    )
    padrao.update(kwargs)
    caso = casos_module.criar_caso(db=banco, **padrao)
    return caso["id"]


def _msg_texto(texto: str) -> dict:
    return {"role": "assistant", "content": texto, "tool_calls": []}


def _msg_tool_call(nome: str, args: dict) -> dict:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [{"id": "c1", "function": {"name": nome, "arguments": json.dumps(args, ensure_ascii=False)}}],
    }


class _ClienteRoteirizado:
    """Stub de OpenRouterClient: devolve a proxima mensagem do roteiro a
    cada chamada; registra tokens no `custo` REAL que `cabeca.investigar()`
    criou (ver `_patch_cliente` -- a fabrica injeta o `custo` verdadeiro aqui,
    do mesmo jeito que o `OpenRouterClient` real o receberia)."""

    def __init__(self, roteiro: list[dict]) -> None:
        self.roteiro = roteiro
        self.chamadas = 0
        self.custo = CustoAcumulado()

    async def chat(self, model, messages, tools=None, tool_choice=None, temperature=0.2):
        self.chamadas += 1
        if self.chamadas > len(self.roteiro):
            raise AssertionError("roteiro esgotado -- cabeca/worker chamou o modelo alem do previsto")
        self.custo.registrar({"prompt_tokens": 50, "completion_tokens": 10})
        return self.roteiro[self.chamadas - 1]

    async def aclose(self) -> None:
        pass


def _patch_cliente(monkeypatch: pytest.MonkeyPatch, cliente_stub: _ClienteRoteirizado) -> None:
    """`investigar()` cria seu proprio `CustoAcumulado` e o passa ao
    `OpenRouterClient(...)`; a fabrica abaixo substitui a classe real pelo
    stub, mas religa `cliente_stub.custo` ao `custo` de VERDADE que
    `investigar()` criou -- assim os guardrails de teto (que leem
    `resultado.custo`) veem os mesmos tokens que o stub registrou."""

    def _factory(api_key, base_url, custo, client=None, **kwargs):
        cliente_stub.custo = custo
        return cliente_stub

    monkeypatch.setattr(cabeca, "OpenRouterClient", _factory)


# --------------------------------------------------------------------------- #
# planejar()
# --------------------------------------------------------------------------- #


async def test_planejar_parseia_definir_plano(caso_db):
    caso_id = _caso(caso_db)
    caso = casos_module.obter_caso(caso_id, db=caso_db)
    roteiro = [
        _msg_tool_call(
            "definir_plano",
            {
                "subtarefas": [
                    {"municipio": "trindade", "descricao": "Contratos do CNPJ X", "instrucao": "Busque..."},
                ]
            },
        )
    ]
    cliente = _ClienteRoteirizado(roteiro)
    subtarefas = await cabeca.planejar(cliente, "modelo-cabeca", caso, "descricao livre", max_subtarefas=20)
    assert len(subtarefas) == 1
    assert subtarefas[0]["id"] == "st_001"
    assert subtarefas[0]["municipio"] == "trindade"


async def test_planejar_sem_tool_call_vira_semplano(caso_db):
    caso_id = _caso(caso_db)
    caso = casos_module.obter_caso(caso_id, db=caso_db)
    cliente = _ClienteRoteirizado([_msg_texto("desculpe, nao decompus nada")])
    with pytest.raises(cabeca.SemPlano):
        await cabeca.planejar(cliente, "modelo-cabeca", caso, "descricao", max_subtarefas=20)


async def test_planejar_trunca_no_teto_de_subtarefas(caso_db):
    caso_id = _caso(caso_db)
    caso = casos_module.obter_caso(caso_id, db=caso_db)
    muitas = [{"municipio": "trindade", "descricao": f"st {i}", "instrucao": "x"} for i in range(5)]
    cliente = _ClienteRoteirizado([_msg_tool_call("definir_plano", {"subtarefas": muitas})])
    subtarefas = await cabeca.planejar(cliente, "modelo-cabeca", caso, "descricao", max_subtarefas=2)
    assert len(subtarefas) == 2


async def test_extrair_periodo_encontra_min_e_max_dos_anos_citados():
    assert cabeca._extrair_periodo("Contratos vigentes em 2024 e 2025, com dispensa.") == (2024, 2025)


def test_extrair_periodo_sem_ano_devolve_none():
    assert cabeca._extrair_periodo("Investigar o fornecedor Leite Advogados em Trindade.") is None


def test_extrair_periodo_ano_unico():
    assert cabeca._extrair_periodo("Folha de junho de 2024 do servidor X.") == (2024, 2024)


async def test_planejar_anexa_periodo_extraido_e_nota_na_instrucao(caso_db):
    """F7: a cabeca extrai o periodo do texto do caso e anexa (a) o campo
    'periodo' estruturado na subtarefa e (b) uma nota textual na instrucao --
    a filtragem de verdade acontece em codigo (agente/tools.py), isto aqui
    so garante que a subtarefa carrega a informacao."""
    caso_id = _caso(caso_db)
    caso = casos_module.obter_caso(caso_id, db=caso_db)
    roteiro = [
        _msg_tool_call(
            "definir_plano",
            {
                "subtarefas": [
                    {"municipio": "trindade", "descricao": "Contratos e empenhos", "instrucao": "Busque contratos."},
                ]
            },
        )
    ]
    cliente = _ClienteRoteirizado(roteiro)
    subtarefas = await cabeca.planejar(
        cliente, "modelo-cabeca", caso, "contratos vigentes, empenhos, dispensa 2024 e 2025", max_subtarefas=20
    )
    assert subtarefas[0]["periodo"] == [2024, 2025]
    assert "2024" in subtarefas[0]["instrucao"] and "2025" in subtarefas[0]["instrucao"]


async def test_planejar_sem_periodo_no_texto_deixa_periodo_none(caso_db):
    caso_id = _caso(caso_db)
    caso = casos_module.obter_caso(caso_id, db=caso_db)
    roteiro = [
        _msg_tool_call(
            "definir_plano",
            {"subtarefas": [{"municipio": "trindade", "descricao": "Contratos do CNPJ X", "instrucao": "Busque..."}]},
        )
    ]
    cliente = _ClienteRoteirizado(roteiro)
    subtarefas = await cabeca.planejar(cliente, "modelo-cabeca", caso, "contratos do fornecedor X", max_subtarefas=20)
    assert subtarefas[0]["periodo"] is None


async def test_planejar_loga_a_tool_call_definir_plano(caso_db):
    """Guardrail §6.2 #6 (review R4, F1): o `definir_plano` da cabeca tambem
    e uma tool-call e fica no rastro de auditoria do caso."""
    caso_id = _caso(caso_db)
    caso = casos_module.obter_caso(caso_id, db=caso_db)
    roteiro = [
        _msg_tool_call(
            "definir_plano",
            {"subtarefas": [{"municipio": "trindade", "descricao": "st1", "instrucao": "x"}]},
        )
    ]
    cliente = _ClienteRoteirizado(roteiro)
    await cabeca.planejar(cliente, "modelo-cabeca", caso, "descricao", max_subtarefas=20)

    entradas = log_module.ler_log(caso_id)
    assert len(entradas) == 1
    assert entradas[0]["tool"] == "definir_plano"
    assert entradas[0]["subtarefa_id"] == "planejamento"
    assert entradas[0]["is_error"] is False
    assert "1 subtarefa" in entradas[0]["resultado_resumo"]


# --------------------------------------------------------------------------- #
# _validar_evidencias() -- deterministico
# --------------------------------------------------------------------------- #


def test_validar_evidencias_aceita_evidencia_real_do_manifesto(caso_db):
    caso_id = _caso(caso_db)
    evidencia.registrar_evidencia(
        caso_id,
        {"tipo": "pdf", "municipio": "trindade", "secao": "contratos", "rotulo": "x",
         "url_origem": "https://x", "caminho_local": "a.pdf", "sha256": "abc", "bytes": 1, "content_type": "application/pdf"},
    )
    ev_id = evidencia.ler_manifesto(caso_id)[0]["evidencia_id"]
    resultado = ResultadoSubtarefa(subtarefa_id="st_001", sucesso=True, resumo="ok", evidencia_ids=[ev_id])
    ok, motivo = cabeca._validar_evidencias(caso_id, resultado)
    assert ok is True
    assert motivo is None


def test_validar_evidencias_rejeita_evidencia_inventada(caso_db):
    caso_id = _caso(caso_db)
    resultado = ResultadoSubtarefa(subtarefa_id="st_001", sucesso=True, resumo="ok", evidencia_ids=["ev_999999"])
    ok, motivo = cabeca._validar_evidencias(caso_id, resultado)
    assert ok is False
    assert "ev_999999" in (motivo or "")


def test_validar_evidencias_aceita_sucesso_sem_evidencia(caso_db):
    caso_id = _caso(caso_db)
    resultado = ResultadoSubtarefa(subtarefa_id="st_001", sucesso=True, resumo="nada encontrado")
    ok, motivo = cabeca._validar_evidencias(caso_id, resultado)
    assert ok is True


def test_validar_evidencias_rejeita_falha_do_worker(caso_db):
    caso_id = _caso(caso_db)
    resultado = ResultadoSubtarefa(subtarefa_id="st_001", sucesso=False, resumo="falhou", motivo_falha="teto_iteracoes")
    ok, motivo = cabeca._validar_evidencias(caso_id, resultado)
    assert ok is False
    assert motivo == "teto_iteracoes"


# --------------------------------------------------------------------------- #
# _saneiar_sintese() -- guardrail F2 (review R4): numero so passa se aparecer
# nos dados ESTRUTURADOS reais do caso (nao so no texto livre do worker)
# --------------------------------------------------------------------------- #


def test_saneiar_sintese_mantem_numero_que_bate_com_item_real(caso_db):
    caso_id = _caso(caso_db)
    casos_module.adicionar_item(
        caso_id, "trindade", "contratos",
        {"titulo": "0343/26", "documento": "45.160.810/0001-43", "valor": "3.750.000", "data": "06/07/2026",
         "ref_registro": {"id": "reg-1"}, "raw": {}},
        db=caso_db,
    )
    caso = casos_module.obter_caso(caso_id, db=caso_db)
    texto = "Foi encontrado o contrato 0343/26 (CNPJ 45.160.810/0001-43) no valor de 3.750.000."
    saneado = cabeca._saneiar_sintese(texto, caso_id, caso)
    assert saneado == texto  # tudo verificavel -- nada trocado


def test_saneiar_sintese_troca_numero_inventado_por_nao_verificado(caso_db):
    caso_id = _caso(caso_db)
    casos_module.adicionar_item(
        caso_id, "trindade", "contratos",
        {"titulo": "0343/26", "documento": "45.160.810/0001-43", "valor": "3.750.000", "data": "06/07/2026",
         "ref_registro": {"id": "reg-1"}, "raw": {}},
        db=caso_db,
    )
    caso = casos_module.obter_caso(caso_id, db=caso_db)
    # 9.999.999 nao aparece em nenhum item/manifesto real -- o worker/LLM
    # inventou esse valor (exatamente o cenario que F2 aponta como furo).
    texto = "O contrato somou 9.999.999 em valores nao encontrados no dossie."
    saneado = cabeca._saneiar_sintese(texto, caso_id, caso)
    assert "9.999.999" not in saneado
    assert "[não verificado]" in saneado


def test_saneiar_sintese_conta_de_itens_bate_com_estruturado(caso_db):
    caso_id = _caso(caso_db)
    for i in range(3):
        casos_module.adicionar_item(
            caso_id, "trindade", "contratos",
            {"titulo": f"000{i}/26", "valor": "1.000,00", "ref_registro": {"id": f"reg-{i}"}, "raw": {}},
            db=caso_db,
        )
    caso = casos_module.obter_caso(caso_id, db=caso_db)
    texto = "Foram encontrados 3 contratos no total."
    saneado = cabeca._saneiar_sintese(texto, caso_id, caso)
    assert saneado == texto  # "3" bate com len(itens) -- contagem real


def test_saneiar_sintese_contagem_forjada_vira_nao_verificado(caso_db):
    caso_id = _caso(caso_db)
    casos_module.adicionar_item(
        caso_id, "trindade", "contratos",
        {"titulo": "0001/26", "valor": "1.000,00", "ref_registro": {"id": "reg-1"}, "raw": {}},
        db=caso_db,
    )
    caso = casos_module.obter_caso(caso_id, db=caso_db)
    # so ha 1 item persistido -- "42" nao corresponde a nenhuma contagem real.
    texto = "Foram encontrados 42 contratos no total."
    saneado = cabeca._saneiar_sintese(texto, caso_id, caso)
    assert "42" not in saneado
    assert "[não verificado]" in saneado


def test_saneiar_sintese_nao_mexe_em_sha256_ja_validado(caso_db):
    caso_id = _caso(caso_db)
    ev = evidencia.registrar_evidencia(
        caso_id,
        {"tipo": "pdf", "municipio": "trindade", "secao": "contratos", "rotulo": "x",
         "url_origem": "https://x", "caminho_local": "a.pdf", "sha256": "abc123def456",
         "bytes": 1, "content_type": "application/pdf"},
    )
    caso = casos_module.obter_caso(caso_id, db=caso_db)
    texto = f"Evidencia com hash `{ev['sha256']}` confirmada."
    saneado = cabeca._saneiar_sintese(texto, caso_id, caso)
    assert ev["sha256"] in saneado  # o hash real sobrevive intacto (nao vira [nao verificado])


# --------------------------------------------------------------------------- #
# investigar() fim a fim (sem rede)
# --------------------------------------------------------------------------- #


async def test_investigar_fim_a_fim_com_evidencia_real_gera_relatorio(caso_db, monkeypatch: pytest.MonkeyPatch):
    caso_id = _caso(caso_db)

    async def _fake_executar_tool(nome, args, *, caso_id, periodo=None):
        assert nome == "buscar_entidade"
        evidencia.registrar_evidencia(
            caso_id,
            {
                "tipo": "pdf", "municipio": "trindade", "secao": "contratos", "rotulo": "Contrato 1",
                "url_origem": "https://x/api", "caminho_local": "a.pdf", "sha256": "cafe1234",
                "bytes": 10, "content_type": "application/pdf", "item_id": "",
            },
        )
        return {"grupos": [], "avisos": []}

    monkeypatch.setattr("busca_go.agente.worker.executar_tool", _fake_executar_tool)

    ev_id_esperado = "ev_000001"
    roteiro = [
        _msg_tool_call(
            "definir_plano",
            {"subtarefas": [{"municipio": "trindade", "descricao": "Contratos do CNPJ X", "instrucao": "Busque contratos."}]},
        ),
        _msg_tool_call("buscar_entidade", {"slug": "trindade", "cnpj": "02292266000180"}),
        _msg_tool_call(
            "finalizar_subtarefa",
            {"sucesso": True, "resumo": "1 contrato encontrado com anexo baixado.", "evidencia_ids": [ev_id_esperado]},
        ),
        _msg_texto("Foi encontrado 1 contrato do CNPJ pesquisado em Trindade."),
    ]
    cliente_stub = _ClienteRoteirizado(roteiro)
    _patch_cliente(monkeypatch, cliente_stub)

    resultado = await cabeca.investigar(
        caso_id,
        "Investigar contratos do CNPJ 02.292.266/0001-80 em Trindade.",
        api_key="chave-teste",
        base_url="https://openrouter.ai/api/v1",
        modelo_cabeca="google/gemini-3-flash",
        modelo_worker="deepseek/deepseek-v4-flash",
        max_subtarefas=20,
        max_iter_worker=8,
        teto_tokens=None,
        teto_tempo_s=None,
        db=caso_db,
    )

    assert resultado.lacunas == []
    assert len(resultado.subtarefas_executadas) == 1
    assert resultado.teto_atingido is False
    assert "Foi encontrado 1 contrato" in resultado.relatorio_md
    assert "cafe1234" in resultado.relatorio_md  # sha256 real passou pelo saneamento
    assert "## Lacunas e ressalvas" in resultado.relatorio_md
    assert "## Índice de evidências" in resultado.relatorio_md
    assert "tokens" in resultado.relatorio_md
    import pathlib
    assert pathlib.Path(resultado.relatorio_path).read_text(encoding="utf-8") == resultado.relatorio_md


async def test_investigar_subtarefa_falha_2x_vira_lacuna_no_relatorio(caso_db, monkeypatch: pytest.MonkeyPatch):
    caso_id = _caso(caso_db)

    roteiro = [
        _msg_tool_call(
            "definir_plano",
            {"subtarefas": [{"municipio": "municipio-fantasma", "descricao": "Secao inexistente", "instrucao": "x"}]},
        ),
        # tentativa 1: worker finaliza afirmando uma evidencia que NAO existe no manifesto
        _msg_tool_call("finalizar_subtarefa", {"sucesso": True, "resumo": "achei", "evidencia_ids": ["ev_999999"]}),
        # tentativa 2 (reexecucao): mesma alucinacao
        _msg_tool_call("finalizar_subtarefa", {"sucesso": True, "resumo": "achei de novo", "evidencia_ids": ["ev_999999"]}),
        # redacao do relatorio
        _msg_texto("Nao foi possivel confirmar achados neste municipio."),
    ]
    cliente_stub = _ClienteRoteirizado(roteiro)
    _patch_cliente(monkeypatch, cliente_stub)

    resultado = await cabeca.investigar(
        caso_id,
        "Caso com subtarefa impossivel.",
        api_key="chave-teste",
        base_url="https://openrouter.ai/api/v1",
        modelo_cabeca="google/gemini-3-flash",
        modelo_worker="deepseek/deepseek-v4-flash",
        max_subtarefas=20,
        max_iter_worker=8,
        db=caso_db,
    )

    assert resultado.subtarefas_executadas == []
    assert len(resultado.lacunas) == 1
    assert "ev_999999" in resultado.lacunas[0].motivo
    assert "[não verificado]" in resultado.relatorio_md
    assert "Secao inexistente" in resultado.relatorio_md


async def test_investigar_planejamento_falho_vira_lacuna_mas_ainda_redige(caso_db, monkeypatch: pytest.MonkeyPatch):
    caso_id = _caso(caso_db)
    roteiro = [
        _msg_texto("nao consigo planejar"),  # planejar() -> SemPlano
        _msg_texto("Nenhum achado -- planejamento falhou."),  # redacao
    ]
    cliente_stub = _ClienteRoteirizado(roteiro)
    _patch_cliente(monkeypatch, cliente_stub)

    resultado = await cabeca.investigar(
        caso_id, "Caso qualquer.", api_key="k", base_url="https://x", modelo_cabeca="a", modelo_worker="b",
        max_subtarefas=5, max_iter_worker=4, db=caso_db,
    )
    assert len(resultado.lacunas) == 1
    assert resultado.lacunas[0].subtarefa_id == "planejamento"
    assert resultado.relatorio_path


async def test_investigar_teto_de_tokens_interrompe_e_marca_parcial(caso_db, monkeypatch: pytest.MonkeyPatch):
    caso_id = _caso(caso_db)
    roteiro = [
        _msg_tool_call(
            "definir_plano",
            {
                "subtarefas": [
                    {"municipio": "trindade", "descricao": "st1", "instrucao": "x"},
                    {"municipio": "trindade", "descricao": "st2", "instrucao": "y"},
                ]
            },
        ),
        _msg_texto("relatorio parcial"),
    ]
    cliente_stub = _ClienteRoteirizado(roteiro)
    _patch_cliente(monkeypatch, cliente_stub)

    resultado = await cabeca.investigar(
        # teto MENOR que os 60 tokens que a propria chamada de planejamento ja
        # consome (`_ClienteRoteirizado.chat` registra 50+10 por chamada) --
        # nenhuma subtarefa chega a rodar (cada uma checa o teto antes).
        caso_id, "Caso caro.", api_key="k", base_url="https://x", modelo_cabeca="a", modelo_worker="b",
        max_subtarefas=5, max_iter_worker=4, teto_tokens=50, db=caso_db,
    )
    assert resultado.teto_atingido is True
    assert len(resultado.lacunas) == 2
    assert all("teto de tokens" in lac.motivo for lac in resultado.lacunas)
    assert "Teto de custo/tempo atingido" in resultado.relatorio_md
