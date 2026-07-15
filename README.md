# busca-transparencia-goias

Hub de consulta de transparencia publica dos municipios goianos que usam o portal
**acessoainformacao.\<municipio\>.go.gov.br** (plataforma **NucleoGov**).

## Municipios cobertos (6)

`rioverde`, `senadorcanedo`, `trindade`, `cristalina`, `itumbiara`,
`saomigueldoaraguaia` — todos NucleoGov, com rotas reais confirmadas AO VIVO
(2026-07-07) e mapeadas em `busca_go/nucleo/routes.py`.

> Goiania e Aparecida de Goiania **nao** fazem parte do projeto: nao usam
> NucleoGov (rodam sistemas externos). O porque esta documentado em
> `AUDITORIA/rotas/goiania.md` e `AUDITORIA/rotas/aparecida.md`.

## Secoes (catalogo canonico, 10)

licitacoes, dispensas, contratos, aditamentos, despesas, receitas, folha,
legislacao, sancoes, atas de registro de preco.

- **`aditamentos` e PER-MUNICIPIO.** Em Cristalina, Itumbiara e Sao Miguel do
  Araguaia e uma secao propria, com pagina-lista dedicada (slug real
  `aditivos`, ex.: `informacao/aditivos_cnt`). Em Rio Verde, Senador Canedo e
  Trindade **nao** tem pagina propria — os termos aditivos aparecem so como
  linhas dentro da tabela de **`contratos`**. Por isso a seção esta no catalogo,
  mas so e oferecida (`/api/secoes/<slug>`) onde ha rota real.
- **`legislacao` pode ter varias sub-paginas**, concatenadas num unico
  resultado (cada item com sua `fonte`): Cristalina 4 (leis, decretos,
  portarias, resolucoes), Trindade 3 (leis, decretos, portarias), Itumbiara 3
  (portarias, decretos, resolucoes), Senador Canedo 2 (portarias, decretos),
  Sao Miguel 2 (portarias, decretos). Em **Sao Miguel as LEIS ficam num CMS
  externo** (fora do host `acessoainformacao`, sem tabela HTML) e por isso
  estao fora do escopo deste scraper — so as sub-paginas NucleoGov entram.
- **`atas` (registro de preco) so existe** em Rio Verde, Trindade e Sao Miguel;
  nos demais e apenas filtro dentro de licitacoes/contratos, sem rota propria.

## Como o roteamento funciona (tabela explicita)

Nao existe um template unico de URL que sirva a todos os portais: cada
municipio tem rotas proprias, e ate dentro do mesmo municipio o prefixo varia
por secao (`cidadao/informacao/...`, `cidadao/transparencia/cnt...`,
`cidadao/legislacao/...`, sufixos `_frl`/`_psc`, rota legada `/informacao/...`
sem `cidadao/`, e ate rota por id `mp/id=1`). Por isso o roteamento e uma
**tabela estatica** (`ROTAS` em `busca_go/nucleo/routes.py`), montada path a
path a partir dos relatorios em `AUDITORIA/rotas/*.md` — nunca um pattern
deduzido. Para ajustar/adicionar uma rota, edite essa tabela com base numa
fonte confirmada ao vivo.

## Instalacao

```bash
# 1. Dependencias Python
pip install -e .

# 2. Chromium do Playwright (~150MB, uma vez)
playwright install chromium

# 3. Config
cp .env.example .env
```

## Uso rapido (CLI)

```bash
# Lista municipios conhecidos e status
busca-go municipios

# Lista secoes disponiveis em um municipio (da tabela estatica de rotas reais)
busca-go secoes senadorcanedo

# Consulta licitacoes
busca-go licitacoes senadorcanedo --ano 2025

# Consulta contratos por CNPJ
busca-go contratos trindade --cnpj 11.222.333/0001-81

# Sobe a interface web local em http://localhost:8000
busca-go web
```

Toda resposta indica `source_url` (de onde o dado veio) e `cached_at` (se veio
do cache local SQLite, TTL 7 dias).

## Estrutura

```
busca_go/
  cli.py          # Click (ponto de entrada: `busca-go ...`)
  api.py          # FastAPI (`busca-go web` sobe em http://localhost:8000)
  municipios.py   # registry dos 3 municipios NucleoGov
  nucleo/
    client.py     # Playwright wrapper (async, browser singleton)
    parsers.py    # HTML renderizado -> dataclasses
    routes.py     # tabela estatica (municipio, secao) -> path(s) reais
    sections/     # 1 arquivo por secao (licitacoes, contratos, ...)
  cache.py        # SQLite + TTL
  web/
    index.html    # form + tabela
data/             # cache SQLite + logs
tests/            # smoke tests
```

## Adicionar municipio

O roteamento e por tabela estatica confirmada ao vivo — nao ha descoberta
automatica de menu. Para incluir um novo municipio NucleoGov:

1. Descobrir slug/host: `acessoainformacao.<cidade>.go.gov.br`.
2. Abrir AO VIVO cada secao no portal e anotar o path real de cada uma (as
   rotas variam por secao e por municipio). Registre em `AUDITORIA/rotas/`.
3. Adicionar a entrada em `busca_go/municipios.py` e o mapa `secao -> [paths]`
   em `busca_go/nucleo/routes.py` (`ROTAS`), usando os paths confirmados.
4. Confirmar: `busca-go buscar <slug> licitacoes --human`.

## Limitacoes conhecidas

- Dados dependem do portal estar no ar. Sem fall-back offline alem do cache.
- Via CLI, cada consulta abre 1 navegador Chromium. Via `busca-go web`, o
  Chromium sobe 1 vez no boot (browser compartilhado) e cada requisicao abre
  apenas um context isolado — bem mais leve para uso intenso.
- **WAF por User-Agent headless:** alguns portais (Rio Verde, Trindade)
  respondem **HTTP 403** a qualquer requisicao cujo User-Agent contenha
  `HeadlessChrome` — inclusive na home. O client ja injeta um User-Agent de
  Chrome desktop normal no context (`_UA_CHROME`), o que basta para obter
  **200** em modo headless em todas as rotas confirmadas (verificado ao vivo em
  2026-07-07, inclusive Trindade). Se um portal passar a exigir client-hints
  (`Sec-CH-UA`), a mitigacao de menor custo e rodar aquele host com
  `BUSCA_GO_HEADLESS=false`; nao ha (nem se deve adicionar) evasao/stealth
  agressiva. Quando um portal realmente recusa (403/5xx), a API responde
  **502** com `{"error": "..."}` (nunca finge sucesso com `items: []`) e nada
  e gravado no cache.
- **Soft-block com HTTP 200 nao e detectado (B2):** a deteccao de recusa
  acima cobre apenas status HTTP de erro (403/5xx -> 502). Um portal que
  responda **HTTP 200 com uma pagina de "acesso negado"/login/captcha** (sem
  `<table>` de dados) e indistinguivel de uma secao legitimamente vazia: o
  parser devolve `items: []` e esse vazio e cacheado como sucesso pelo TTL
  (`CACHE_DAYS`). Nao observamos esse comportamento nos portais atuais (usam
  403 real), mas fica registrado como limitacao; mitigar exigiria heuristica
  de deteccao de pagina de erro no corpo 200 (ex.: procurar marcadores de
  login/negacao antes de aceitar o vazio).
- O nucleogov atualiza o JS periodicamente; se o seletor de extracao quebrar,
  ajustar `busca_go/nucleo/parsers.py` (1 lugar).
- Host de transparencia (`acessoainformacao.<slug>.go.gov.br`) nao e
  universal — ex.: Goiania nao resolve nesse padrao. Falha de DNS tambem
  vira 502 com mensagem clara.