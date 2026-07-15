"""Tabela de CAPACIDADE DE BUSCA por (municipio, secao) para a busca por entidade.

Complementa `routes.py`: enquanto ROTAS mapeia o *path* HTML de cada secao
(navegacao por Playwright), esta tabela mapeia como reproduzir o
`POST /api multi_request` de cada secao — o `acao`, o campo de busca textual
(`txtbusca` vs `busca`) e os campos extras (flag de dispensas, periodo de folha).

REGRA ANTI-ALUCINACAO (igual routes.py): so ha entrada CONFIRMADA aqui para
(municipio, secao) que foi exercitado AO VIVO nesta investigacao. Onde nao
confirmado, `resolver()` DERIVA o `acao` do ultimo segmento da rota real
(`routes.ROTAS`) e marca `confirmada=False`; nesse caso a busca server-side e
sempre VALIDADA em runtime (a contagem caiu E os itens contem o termo) antes de
ser confiada — senao cai para varredura + filtro local (ver `entidade.py`).

Evidencia viva (2026-07-07, httpx direto contra os portais reais):
- POST https://acessoainformacao.<slug>.go.gov.br/api
  body: multi_request=true&params={"k1":{"acao":"<acao>","limit":"<off>, <n>",...}}
  resposta: JSON {"k1":{"total":N,"dados":[...]}} — sem CSRF, so UA de desktop.
- senadorcanedo/contratos: `contratos_frl/listar`, campo `txtbusca`
  (nome "FL CONSTRUTORA" 1067->8; CNPJ NAO indexa -> total 0, exige varredura).
- senadorcanedo/licitacoes: `licitacoes_frl/listar`, `txtbusca` (PREGAO 793->583).
- senadorcanedo/dispensas: MESMO acao `licitacoes_frl/listar` + `dispensas=1`
  (569 registros); o acao `dispensas_frl/listar` direto retorna `[]`.
- senadorcanedo/folha: `servidores_frl/listar`, `txtbusca` + ano/mes
  (MARIA ano2026 mes06 -> 650; campo `cpf` vem MASCARADO `xxx.xxx.xxx-xx`).
- trindade/contratos: busca via `contratos/busca_avancada`, campo `busca`
  (PAVSANTOS -> 1; CNPJ nao indexa -> 0); paginacao/varredura por `contratos/listar`.
- trindade/licitacoes: `licitacoes/busca_avancada`/`licitacoes/listar`, `busca`.

Evidencia viva (2026-07-14, httpx + Playwright contra o portal real, item
3L54H3Sr-29 — CALDAZINHA, sabor `_mg`):
- caldazinha/contratos: `contratos_mg/listar`, campo `txtbusca` (mesmo formato
  `{"total":N,"dados":[...]}` das outras cidades; MARIA 1073->26).
- caldazinha/licitacoes: `licitacoes_mg/listar`, `txtbusca` (PREGAO 281->2).
- caldazinha/dispensas: MESMO acao `licitacoes_mg/listar` + `dispensas=1`
  (1898 registros; PUBLICIDADE 1898->8) — o acao `dispensas_mg/listar` direto
  retorna `[]` (nao e um dict k1, e uma lista vazia).
- caldazinha/folha: **NAO** segue o padrao `<slug>/listar` das outras cidades.
  O portal serve a folha por um modulo separado `megasoft` (confirmado via
  interceptacao de rede real da pagina `mgservidores`): acao
  `megasoft/servidores`, paginacao por `pagina`/`tamanhoDaPagina` (nao
  `limit`), resposta em `{"total":N,"registros":[...]}` (nao `dados`), busca
  por nome no campo `nomeDoFuncionario` (nao `txtbusca`), e exige o parametro
  fixo `codigosDoOrgao` (lista de ids de orgao/fundo do municipio — sem ele o
  portal devolve `[]`). Testado ao vivo: `nomeDoFuncionario=ADAO` -> total 1
  (ADAO TESTE DE EXEMPLO, matricula 901, competencia 06/2026). Por isso
  `Capacidade.modo_api="megasoft"` sinaliza `entidade._multi` a usar o
  formato de requisicao/resposta alternativo (ver `entidade.py`).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import routes


@dataclass(frozen=True)
class Capacidade:
    """Como reproduzir o POST multi_request de uma (municipio, secao).

    Atributos:
        acao_listar: acao usado para LISTAR/paginar (retorna dados+total). Base
            da varredura; sempre presente.
        acao_busca: acao usado na busca textual server-side (pode ser o mesmo
            `listar` ou um endpoint dedicado `busca_avancada`). None = sem canal
            de busca server-side (so varredura).
        campo_busca: nome do parametro de busca textual (`txtbusca` ou `busca`).
            None junto com acao_busca=None => sempre varredura.
        extra: parametros SEMPRE enviados nesta secao (ex.: {"dispensas": "1"}).
        periodo: True para folha (aceita ano/mes no payload).
        confirmada: True se exercitada ao vivo; False se derivada da rota.
        modo_api: formato do POST multi_request desta secao.
            - "padrao": `limit="<offset>, <n>"` no request, le `k1.dados` na
              resposta (formato de TODAS as cidades ate 2026-07-07).
            - "megasoft": `pagina`/`tamanhoDaPagina` no request (paginacao por
              numero de pagina, nao offset), le `k1.registros` na resposta.
              Sabor exclusivo da folha de Caldazinha (ver modulo, doc acima).
        modo_anexo: como esta secao expoe o PDF de um registro (download lazy):
            - "detalhe_base64": Senador Canedo. O item da busca NAO tem PDF
              usavel; para listar anexos chama-se `<base>/listarAnexos` e para
              baixar `<base>/downloadAnexo` (PDF vem em base64 no JSON). Ver
              `nucleo/anexos.py`.
            - "embutido_url_assinada": Trindade. O item de `busca_avancada` ja
              traz `anexos:[{id,titulo,download_url}]` (URL S3 assinada, GET
              direto; expira ~40min -> reobter fresco no download).
            - "sem_anexo": secao sem PDF de anexo (ex.: folha).
            - "nao_confirmado": nao exercitado ao vivo -> `anexos.py` DETECTA em
              runtime (item tem download_url? modo B; senao tenta listarAnexos).
    """

    acao_listar: str
    acao_busca: str | None = None
    campo_busca: str | None = None
    extra: dict[str, str] = field(default_factory=dict)
    periodo: bool = False
    confirmada: bool = True
    modo_api: str = "padrao"
    modo_anexo: str = "nao_confirmado"


# Secoes que a busca por entidade varre para CNPJ/CPF/termo (fora folha).
# Ordem = prioridade de exibicao dos grupos.
SECOES_ENTIDADE: list[str] = ["contratos", "dispensas", "licitacoes"]


# Entradas CONFIRMADAS ao vivo. (municipio -> secao -> Capacidade)
CONFIRMADAS: dict[str, dict[str, Capacidade]] = {
    "senadorcanedo": {
        "contratos": Capacidade(
            acao_listar="contratos_frl/listar",
            acao_busca="contratos_frl/listar",
            campo_busca="txtbusca",
            modo_anexo="detalhe_base64",  # listarAnexos+downloadAnexo, ao vivo
        ),
        "licitacoes": Capacidade(
            acao_listar="licitacoes_frl/listar",
            acao_busca="licitacoes_frl/listar",
            campo_busca="txtbusca",
            modo_anexo="detalhe_base64",  # listarAnexos (8 anexos)+downloadAnexo
        ),
        "dispensas": Capacidade(
            acao_listar="licitacoes_frl/listar",
            acao_busca="licitacoes_frl/listar",
            campo_busca="txtbusca",
            extra={"dispensas": "1"},
            # Reusa licitacoes_frl; anexo confirmado ao vivo 2026-07-14 (doc 02
            # §2.1): listarAnexos+downloadAnexo, mesmo modo A de contratos/licitacoes.
            modo_anexo="detalhe_base64",
        ),
        "folha": Capacidade(
            acao_listar="servidores_frl/listar",
            acao_busca="servidores_frl/listar",
            campo_busca="txtbusca",
            periodo=True,
            modo_anexo="sem_anexo",  # folha nao tem PDF de anexo
        ),
    },
    "trindade": {
        "contratos": Capacidade(
            acao_listar="contratos/listar",
            acao_busca="contratos/busca_avancada",
            campo_busca="busca",
            modo_anexo="embutido_url_assinada",  # anexos[].download_url, ao vivo
        ),
        "licitacoes": Capacidade(
            acao_listar="licitacoes/listar",
            acao_busca="licitacoes/busca_avancada",
            campo_busca="busca",
            # Anexo confirmado ao vivo 2026-07-14 (doc 02 §2.1): item real com
            # 5 anexos, mesmo modo B (anexos[].download_url) de contratos.
            modo_anexo="embutido_url_assinada",
        ),
        "folha": Capacidade(
            acao_listar="servidores_cnt/listar",
            acao_busca="servidores_cnt/listar",
            campo_busca="txtbusca",
            periodo=True,
            modo_anexo="sem_anexo",
        ),
    },
    "caldazinha": {
        "contratos": Capacidade(
            acao_listar="contratos_mg/listar",
            acao_busca="contratos_mg/listar",
            campo_busca="txtbusca",
        ),
        "licitacoes": Capacidade(
            acao_listar="licitacoes_mg/listar",
            acao_busca="licitacoes_mg/listar",
            campo_busca="txtbusca",
        ),
        "dispensas": Capacidade(
            acao_listar="licitacoes_mg/listar",
            acao_busca="licitacoes_mg/listar",
            campo_busca="txtbusca",
            extra={"dispensas": "1"},
        ),
        # Sabor "megasoft": paginacao/resposta/campo de busca proprios (ver
        # docstring do modulo e de `modo_api`). `codigosDoOrgao` e fixo — os 5
        # orgaos/fundos do municipio, confirmados ao vivo via
        # `sgmegasoft/listarOrgaos` (Municipio + FUNDEB + Saude + Crianca e
        # Adolescente + Assistencia Social).
        "folha": Capacidade(
            acao_listar="megasoft/servidores",
            acao_busca="megasoft/servidores",
            campo_busca="nomeDoFuncionario",
            extra={"codigosDoOrgao": "22,23,24,25,26"},
            periodo=True,
            modo_api="megasoft",
            modo_anexo="sem_anexo",
        ),
    },
}


def _acao_base(slug: str, secao: str) -> str | None:
    """Deriva o prefixo de acao do ULTIMO segmento da rota real da secao.

    Ex.: rota `cidadao/informacao/contratos_cnt` -> base `contratos_cnt`
    (acao `contratos_cnt/listar`). Retorna None se a secao nao tem rota.
    """
    paths = routes.ROTAS.get(slug, {}).get(secao)
    if not paths:
        return None
    return paths[0].rstrip("/").split("/")[-1]


def resolver(slug: str, secao: str) -> Capacidade:
    """Capacidade de (slug, secao): confirmada se houver; senao derivada da rota.

    Raises:
        routes.SecaoIndisponivel: a secao nao existe no portal deste municipio
            (nem confirmada, nem com rota real derivavel).
    """
    conf = CONFIRMADAS.get(slug, {})
    if secao in conf:
        return conf[secao]
    base = _acao_base(slug, secao)
    if base is None:
        disp = ", ".join(routes.secoes_disponiveis(slug)) or "(nenhuma)"
        raise routes.SecaoIndisponivel(
            f"Secao '{secao}' nao esta disponivel no portal de '{slug}'. "
            f"Secoes disponiveis: {disp}."
        )
    # Derivada: tenta `txtbusca` no proprio listar e VALIDA em runtime.
    return Capacidade(
        acao_listar=f"{base}/listar",
        acao_busca=f"{base}/listar",
        campo_busca="txtbusca",
        periodo=(secao == "folha"),
        confirmada=False,
    )


def acoes_anexo(cap: Capacidade) -> dict[str, str]:
    """Deriva os acaos de anexo (modo A) do prefixo do `acao_listar` da secao.

    Ex.: `contratos_frl/listar` -> base `contratos_frl` -> `listarAnexos` e
    `downloadAnexo`. (Regra do orquestrador: derivar do acao base ja em
    capacidades, nao hardcodear por municipio.) `listarAditivos` NAO entra: ao
    vivo ele nao filtra pelo registro e nao devolve itens baixaveis (ver
    `nucleo/anexos.py::_listar_modo_a`).
    """
    base = cap.acao_listar.split("/", 1)[0]
    return {
        "listar_anexos": f"{base}/listarAnexos",
        "download": f"{base}/downloadAnexo",
    }


def chave_registro_anexo(cap: Capacidade) -> str:
    """Nome do parametro-id que o `listarAnexos` (modo A) espera para o registro.

    Confirmado ao vivo: contratos usam `contrato`, licitacoes/dispensas usam
    `licitacao` (dispensas reusa o acao `licitacoes_frl`). Derivado do prefixo
    do acao base.
    """
    base = cap.acao_listar.split("/", 1)[0]
    if base.startswith("licitac"):
        return "licitacao"
    return "contrato"


__all__ = [
    "Capacidade",
    "CONFIRMADAS",
    "SECOES_ENTIDADE",
    "resolver",
    "acoes_anexo",
    "chave_registro_anexo",
]
