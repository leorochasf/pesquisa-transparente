"""Tools do agente investigador: schemas (function-calling) + dispatcher
validado sobre as funcoes internas JA existentes (blueprint
`AUDITORIA/refatoracao/04-blueprint.md` §2-3, §6.1). O worker nunca chama
`nucleo/*` diretamente -- so por aqui, o que garante que TODO argumento e
validado antes de bater no portal (guardrail §6.2 #1).

5 tools (o blueprint §6.1 lista `listar_anexos`+`baixar_anexo` separados;
aqui os dois viram UMA tool -- `baixar_evidencias_registro`, que ja e
exatamente o que `nucleo/evidencia.py` orquestra: lista TODOS os anexos do
registro e baixa em sequencia controlada, registrando o manifesto. Dividir
em duas so custaria iteracoes do teto curto do worker (§6.2 #2) sem ganho --
a camada de evidencia (P3) ja foi desenhada para nao ser reimplementada
"§2.1: a camada de evidencia nao reimplementa isso"):

- buscar_entidade            -> `nucleo/entidade.pesquisar_combinado` (nome+CNPJ, dedup)
- buscar_despesas_centi      -> `nucleo/centi.buscar_despesas` (so nos 5 municipios Centi)
- buscar_folha                -> `nucleo/entidade.pesquisar` (folha por nome+periodo)
- baixar_evidencias_registro  -> `nucleo/evidencia.baixar_evidencias_registro`
- capturar_screenshot_folha   -> `nucleo/evidencia.capturar_screenshot_folha`

Toda busca que encontra item JA PERSISTE no caso (`nucleo/casos.adicionar_item`)
e devolve `item_id` -- mesmo ponto de encaixe que o job de busca determinista
(P2, `busca_go/api.py::_executar_busca_caso`) usa, entao o dossie do caso fica
identico venha o achado do modo manual ou do agente. O worker recebe de volta
uma versao ENXUTA do item (sem o `raw` inteiro do portal) para nao gastar
tokens do modelo barato com payload que ele nao precisa reler.

ACEIT-F1: `baixar_evidencias_registro` NUNCA aceita `registro` digitado pelo
worker -- so `item_id`. O `registro` completo ({'id','numero','ano'}) e a
secao/municipio sao resolvidos aqui a partir do item ja persistido (fonte:
`casos.obter_item`), o que torna estruturalmente impossivel repetir o bug do
F1 (registro empobrecido, ou id de empenho tratado como registro de
licitacao) -- ver `06-aceitacao-final.md`.

ACEIT-F7: `executar_tool` aceita `periodo` (ano_min, ano_max) extraido pela
cabeca do texto do caso; `_persistir_grupos` descarta (nao persiste) item
cujo ano seja detectavel e caia fora do intervalo -- filtro deterministico,
independente do worker lembrar de aplicar o periodo.
"""

from __future__ import annotations

import re
from typing import Any, Awaitable, Callable

from ..municipios import all_slugs, get as get_municipio
from ..nucleo import anexos, capacidades, casos, centi, entidade, evidencia

_MUNICIPIOS_ENUM = all_slugs()
_DIGITS_RE = re.compile(r"\D+")


class ToolArgumentoInvalido(RuntimeError):
    """Args do tool_call nao passam na validacao (guardrail §6.2 #1):
    municipio fora dos 6, secao inexistente, documento com formato invalido."""


class ToolExecucaoError(RuntimeError):
    """A tool executou com argumentos validos mas o portal/evidencia falhou."""


def _validar_municipio(slug: Any) -> str:
    if not isinstance(slug, str) or slug not in _MUNICIPIOS_ENUM:
        raise ToolArgumentoInvalido(f"'slug' invalido: '{slug}'. Disponiveis: {_MUNICIPIOS_ENUM}.")
    return slug


def _so_digitos(valor: str) -> str:
    return _DIGITS_RE.sub("", valor or "")


def _validar_documento(valor: str, campo: str) -> str:
    digitos = _so_digitos(valor)
    if len(digitos) not in (11, 14):
        raise ToolArgumentoInvalido(
            f"'{campo}' com formato invalido: '{valor}' tem {len(digitos)} digito(s) "
            "(esperado 11 digitos para CPF ou 14 para CNPJ)."
        )
    return digitos


def _validar_periodo(ano: Any, mes: Any, *, obrigatorio: bool) -> tuple[int | None, int | None]:
    if ano is None and mes is None and not obrigatorio:
        return None, None
    if not isinstance(ano, int) or not isinstance(mes, int) or not (1 <= mes <= 12):
        raise ToolArgumentoInvalido("'ano' e 'mes' (1-12) devem ser inteiros validos.")
    return ano, mes


_ANO_RE = re.compile(r"(?:19|20)\d{2}")


def _ano_do_item(item: dict[str, Any]) -> int | None:
    """Extrai o ano do item para o filtro de periodo (F7), tentando na ordem
    mais confiavel: `ref_registro.ano`, `ano` direto (folha), e por ultimo um
    4-digitos dentro de `data`. Item sem ano detectavel NAO e descartado
    (erra para o lado de manter -- so filtra o que da pra confirmar que esta
    fora do periodo, nunca some com um achado por falha de parsing)."""
    ref = item.get("ref_registro")
    if isinstance(ref, dict):
        ano_ref = str(ref.get("ano") or "")
        if _ANO_RE.fullmatch(ano_ref):
            return int(ano_ref)
    ano_direto = item.get("ano")
    if isinstance(ano_direto, int):
        return ano_direto
    if isinstance(ano_direto, str) and _ANO_RE.fullmatch(ano_direto):
        return int(ano_direto)
    data = item.get("data")
    if isinstance(data, str):
        m = _ANO_RE.search(data)
        if m:
            return int(m.group(0))
    return None


def _persistir_grupos(
    caso_id: str,
    slug: str,
    grupos: list[dict[str, Any]],
    avisos: list[str] | None = None,
    periodo: tuple[int, int] | None = None,
) -> dict[str, Any]:
    """Persiste os itens encontrados no caso (mesmo ponto de encaixe do job de
    busca determinista, P2) e devolve uma versao enxuta (sem `raw`) para o
    worker referenciar em `finalizar_subtarefa`.

    F7: quando `periodo` (ano_min, ano_max) vem da cabeca, todo item cujo ano
    seja detectavel e caia FORA do intervalo e descartado (nao persiste,
    nao volta pro worker) -- filtro deterministico, nao depende do worker
    lembrar de aplicar o periodo."""
    grupos_out: list[dict[str, Any]] = []
    avisos_out = list(avisos or [])
    excluidos = 0
    for grupo in grupos:
        secao = grupo["secao"]
        itens_out = []
        for item in grupo.get("itens", []):
            if periodo is not None:
                ano_item = _ano_do_item(item)
                if ano_item is not None and not (periodo[0] <= ano_item <= periodo[1]):
                    excluidos += 1
                    continue
            item_id = casos.adicionar_item(caso_id, slug, secao, item, origem=item.get("origem"))
            itens_out.append(
                {
                    "item_id": item_id,
                    "titulo": item.get("titulo") or item.get("nome"),
                    "documento": item.get("documento") or item.get("matricula"),
                    "valor": item.get("valor") or item.get("liquido"),
                    "data": item.get("data"),
                    "ref_registro": item.get("ref_registro"),
                }
            )
        grupos_out.append({"secao": secao, "total": len(itens_out), "itens": itens_out})
    if excluidos:
        avisos_out.append(
            f"{excluidos} item(ns) fora do periodo {periodo[0]}-{periodo[1]} foram descartados (nao persistidos)."
        )
    return {"grupos": grupos_out, "avisos": avisos_out}


# --------------------------------------------------------------------------- #
# Handlers
# --------------------------------------------------------------------------- #


async def _tool_buscar_entidade(
    args: dict[str, Any], caso_id: str, periodo: tuple[int, int] | None = None
) -> dict[str, Any]:
    slug = _validar_municipio(args.get("slug"))
    nome = (args.get("nome") or "").strip() or None
    cnpj_bruto = (args.get("cnpj") or "").strip() or None
    cnpj = _validar_documento(cnpj_bruto, "cnpj") if cnpj_bruto else None
    if not nome and not cnpj:
        raise ToolArgumentoInvalido("Informe 'nome' e/ou 'cnpj'.")
    try:
        resultado = await entidade.pesquisar_combinado(slug, nome=nome, cnpj=cnpj)
    except entidade.PortalError as exc:
        raise ToolExecucaoError(f"Falha ao buscar entidade em '{slug}': {exc}") from exc
    return _persistir_grupos(caso_id, slug, resultado.get("grupos", []), resultado.get("avisos"), periodo=periodo)


async def _tool_buscar_despesas_centi(
    args: dict[str, Any], caso_id: str, periodo: tuple[int, int] | None = None
) -> dict[str, Any]:
    slug = _validar_municipio(args.get("slug"))
    if slug not in centi.MUNICIPIOS_CENTI:
        raise ToolArgumentoInvalido(
            f"'{slug}' nao usa o backend Centi para despesas; use 'buscar_entidade' "
            "(cobre despesas nesse municipio pelo caminho existente)."
        )
    cpf_cnpj_bruto = (args.get("cpf_cnpj") or "").strip() or None
    credor = (args.get("credor") or "").strip() or None
    cpf_cnpj = _validar_documento(cpf_cnpj_bruto, "cpf_cnpj") if cpf_cnpj_bruto else None
    if not cpf_cnpj and not credor:
        raise ToolArgumentoInvalido("Informe 'cpf_cnpj' e/ou 'credor'.")
    mun = get_municipio(slug)
    cli = entidade._novo_client()
    try:
        itens = await centi.buscar_despesas(cli, mun.url_base, cpf_cnpj=cpf_cnpj, credor=credor)
    except centi.PortalError as exc:
        raise ToolExecucaoError(f"Falha ao buscar despesas Centi em '{slug}': {exc}") from exc
    finally:
        await cli.aclose()
    return _persistir_grupos(caso_id, slug, [{"secao": "despesas", "itens": itens}], periodo=periodo)


async def _tool_buscar_folha(
    args: dict[str, Any], caso_id: str, periodo: tuple[int, int] | None = None
) -> dict[str, Any]:
    slug = _validar_municipio(args.get("slug"))
    nome = (args.get("nome") or "").strip()
    if not nome:
        raise ToolArgumentoInvalido("Informe 'nome' (aceita nome ou matricula do servidor).")
    ano, mes = _validar_periodo(args.get("ano"), args.get("mes"), obrigatorio=False)
    try:
        resultado = await entidade.pesquisar(slug, nome, ano=ano, mes=mes)
    except entidade.PortalError as exc:
        raise ToolExecucaoError(f"Falha ao buscar folha em '{slug}': {exc}") from exc
    grupo_folha = next((g for g in resultado.get("grupos", []) if g["secao"] == "folha"), None)
    grupos = [grupo_folha] if grupo_folha else []
    saida = _persistir_grupos(caso_id, slug, grupos, resultado.get("avisos"), periodo=periodo)
    if grupo_folha is None:
        saida["avisos"].append(f"Nenhum registro de folha para '{nome}' em '{slug}'.")
    return saida


async def _tool_baixar_evidencias_registro(
    args: dict[str, Any], caso_id: str, periodo: tuple[int, int] | None = None
) -> dict[str, Any]:
    """F1: a UNICA entrada aceita e o `item_id` de um item JA persistido por
    'buscar_entidade' -- o registro completo ({'id','numero','ano'}) e a
    secao/municipio sao resolvidos AQUI, a partir do dado real gravado no
    caso, nunca re-digitados pelo worker LLM. Isso torna estruturalmente
    impossivel repetir o bug do F1 (registro empobrecido `{'id':'517'}`, ou
    id de empenho passado como registro de licitacao)."""
    item_id = str(args.get("item_id") or "").strip()
    if not item_id:
        raise ToolArgumentoInvalido(
            "Informe 'item_id' -- o item_id que 'buscar_entidade' devolveu para o "
            "registro (contrato/dispensa/licitacao) cujos anexos voce quer baixar. "
            "Nao monte um 'registro' manualmente; use o item_id ja coletado."
        )
    item = casos.obter_item(item_id)
    if item is None or item.get("caso_id") != caso_id:
        raise ToolArgumentoInvalido(
            f"'item_id' invalido: '{item_id}' nao pertence a este caso. Use o item_id "
            "que 'buscar_entidade' devolveu para o registro que voce quer baixar."
        )
    secao = item.get("secao")
    if secao not in capacidades.SECOES_ENTIDADE:
        raise ToolArgumentoInvalido(
            f"O item '{item_id}' e da secao '{secao}', que nao tem PDFs para baixar "
            f"(so {capacidades.SECOES_ENTIDADE} tem anexos baixaveis). Itens de "
            "despesas/empenhos (buscar_despesas_centi) e de folha (buscar_folha) "
            "nao tem registro de licitacao/contrato/dispensa para anexar -- nao "
            "chame esta tool para eles."
        )
    registro = item.get("ref_registro")
    if (
        not isinstance(registro, dict)
        or not str(registro.get("id") or "").strip()
        or not str(registro.get("numero") or "").strip()
    ):
        raise ToolArgumentoInvalido(
            f"O item '{item_id}' nao tem identificadores completos (id e numero do "
            "registro) para localizar os anexos no portal -- provavelmente nao veio "
            "de 'buscar_entidade'. Nao ha como baixar evidencias para ele."
        )
    slug = item.get("municipio")
    try:
        resultado = await evidencia.baixar_evidencias_registro(
            caso_id, slug, secao, registro, item_id=item_id, db=casos.default_db()
        )
    except LookupError as exc:
        # KeyError (municipio) ou SecaoIndisponivel (routes.py, LookupError) --
        # problema de argumento, nao de portal.
        raise ToolArgumentoInvalido(str(exc)) from exc
    except (anexos.AnexoError, entidade.PortalError) as exc:
        raise ToolExecucaoError(f"Falha ao baixar evidencias em '{slug}/{secao}': {exc}") from exc
    return {
        "evidencia_ids": [e["evidencia_id"] for e in resultado.baixados],
        "falhas": resultado.falhas,
        "pendentes": len(resultado.pendentes),
        "teto_atingido": resultado.teto_atingido,
    }


async def _tool_capturar_screenshot_folha(
    args: dict[str, Any], caso_id: str, periodo: tuple[int, int] | None = None
) -> dict[str, Any]:
    slug = _validar_municipio(args.get("slug"))
    nome = (args.get("nome") or "").strip()
    if not nome:
        raise ToolArgumentoInvalido("Informe 'nome' (aceita nome ou matricula do servidor).")
    ano, mes = _validar_periodo(args.get("ano"), args.get("mes"), obrigatorio=True)
    matricula = (args.get("matricula") or "").strip() or None
    item_id = args.get("item_id") or None
    try:
        resultado = await evidencia.capturar_screenshot_folha(
            caso_id, slug, nome, ano, mes, matricula=matricula, item_id=item_id, db=casos.default_db()
        )
    except evidencia.EvidenciaError as exc:
        raise ToolExecucaoError(f"Falha ao capturar screenshot de folha em '{slug}': {exc}") from exc
    # A entrada 'json' do manifesto (dados estruturados do print) e escrita
    # por `capturar_screenshot_folha` mas nao volta no dataclass -- localizada
    # aqui via `evidencia_relacionada` (leitura do manifesto, sem reimplementar).
    manifesto = evidencia.ler_manifesto(caso_id)
    ev_json = next(
        (e["evidencia_id"] for e in manifesto if e.get("evidencia_relacionada") == resultado.png["evidencia_id"]),
        None,
    )
    evidencia_ids = [resultado.png["evidencia_id"]] + ([ev_json] if ev_json else [])
    return {"evidencia_ids": evidencia_ids, "avisos": resultado.avisos}


_HANDLERS: dict[str, Callable[[dict[str, Any], str, "tuple[int, int] | None"], Awaitable[dict[str, Any]]]] = {
    "buscar_entidade": _tool_buscar_entidade,
    "buscar_despesas_centi": _tool_buscar_despesas_centi,
    "buscar_folha": _tool_buscar_folha,
    "baixar_evidencias_registro": _tool_baixar_evidencias_registro,
    "capturar_screenshot_folha": _tool_capturar_screenshot_folha,
}


async def executar_tool(
    nome: str, args: dict[str, Any], *, caso_id: str, periodo: tuple[int, int] | None = None
) -> dict[str, Any]:
    """Ponto unico de execucao de tool: valida `nome`/`args` (guardrail §6.2 #1)
    antes de despachar para o handler correspondente.

    `periodo` (F7): (ano_min, ano_max) que a cabeca extraiu do caso, repassado
    pelo worker (`agente/worker.py`) para os handlers que persistem itens --
    itens fora do intervalo sao descartados em `_persistir_grupos`, nao
    dependem do worker lembrar de filtrar."""
    handler = _HANDLERS.get(nome)
    if handler is None:
        raise ToolArgumentoInvalido(f"Tool desconhecida: '{nome}'. Disponiveis: {sorted(_HANDLERS)}.")
    if not isinstance(args, dict):
        raise ToolArgumentoInvalido("Argumentos da tool devem ser um objeto JSON.")
    return await handler(args, caso_id, periodo)


# --------------------------------------------------------------------------- #
# Schemas (OpenAI-compativel function-calling)
# --------------------------------------------------------------------------- #

TOOL_SCHEMAS_WORKER: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "buscar_entidade",
            "description": (
                "Busca contratos/dispensas/licitacoes/despesas de um fornecedor por "
                "nome e/ou CNPJ num municipio, deduplicando e persistindo os achados "
                "no caso. Informe nome E cnpj quando souber os dois -- maximiza "
                "cobertura sem contar o mesmo registro duas vezes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string", "enum": _MUNICIPIOS_ENUM},
                    "nome": {"type": "string", "description": "Nome/razao social do fornecedor."},
                    "cnpj": {"type": "string", "description": "CNPJ, com ou sem mascara."},
                },
                "required": ["slug"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_despesas_centi",
            "description": (
                "Busca despesas/empenhos direto no backend Centi (1 chamada, sem "
                "paginar) -- SO funciona nos municipios que usam esse backend "
                "(nao inclui Senador Canedo; para Senador Canedo use buscar_entidade)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string", "enum": sorted(centi.MUNICIPIOS_CENTI)},
                    "cpf_cnpj": {"type": "string", "description": "CPF ou CNPJ do credor, com ou sem mascara."},
                    "credor": {"type": "string", "description": "Nome (ou trecho do nome) do credor."},
                },
                "required": ["slug"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_folha",
            "description": (
                "Busca a folha de pagamento de um servidor (por nome ou matricula) "
                "num municipio, opcionalmente filtrando ano/mes, e persiste os "
                "registros encontrados no caso."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string", "enum": _MUNICIPIOS_ENUM},
                    "nome": {"type": "string", "description": "Nome ou matricula do servidor."},
                    "ano": {"type": "integer"},
                    "mes": {"type": "integer", "minimum": 1, "maximum": 12},
                },
                "required": ["slug", "nome"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "baixar_evidencias_registro",
            "description": (
                "Baixa TODOS os anexos (PDF) de UM registro (contrato/dispensa/"
                "licitacao) ja encontrado por 'buscar_entidade' e registra cada um "
                "no manifesto de evidencias do caso, com sha256. Informe APENAS o "
                "'item_id' que 'buscar_entidade' devolveu para esse item -- o "
                "sistema resolve automaticamente municipio/secao/identificadores a "
                "partir do item ja persistido no caso (nao monte 'registro' na mao). "
                "So funciona para itens de contratos/dispensas/licitacoes -- NAO "
                "funciona para itens de despesas/empenhos nem de folha."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "item_id": {
                        "type": "string",
                        "description": "item_id devolvido por 'buscar_entidade' para o registro cujos anexos voce quer baixar.",
                    },
                },
                "required": ["item_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "capturar_screenshot_folha",
            "description": (
                "Captura o lastro de UM mes de folha (screenshot da pagina filtrada "
                "+ JSON dos valores + link da secao + sha256) -- nao existe URL "
                "direta para holerite, este e o lastro citavel (Decisao 2 do dono). "
                "Ano e mes sao obrigatorios (competencia especifica)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string", "enum": _MUNICIPIOS_ENUM},
                    "nome": {"type": "string", "description": "Nome ou matricula do servidor."},
                    "ano": {"type": "integer"},
                    "mes": {"type": "integer", "minimum": 1, "maximum": 12},
                    "matricula": {"type": "string", "description": "Filtro adicional para desambiguar homonimos."},
                    "item_id": {"type": "string"},
                },
                "required": ["slug", "nome", "ano", "mes"],
            },
        },
    },
]


__all__ = [
    "ToolArgumentoInvalido",
    "ToolExecucaoError",
    "TOOL_SCHEMAS_WORKER",
    "executar_tool",
]
