---
name: Busca Transparência Goiás
description: Hub de busca unificada nos portais de transparência de municípios goianos — direção visual "O Códice".
colors:
  # Valores canônicos do tema CLARO (padrão). O tema ESCURO completo está na seção Colors como
  # bloco `.dark` — são tokens distintos, não duplicação. OKLCH é a fonte da verdade (doutrina do projeto);
  # o linter do Stitch emite apenas um warning para não-hex, aceito aqui de propósito.
  bg: "oklch(1 0 0)"
  surface: "oklch(0.985 0.005 40)"
  surface-2: "oklch(0.962 0.006 40)"
  border: "oklch(0.892 0.007 40)"
  border-interactive: "oklch(0.64 0.012 40)"
  ink: "oklch(0.26 0.014 38)"
  muted: "oklch(0.475 0.012 40)"
  primary-oxblood: "oklch(0.47 0.108 36)"
  primary-oxblood-hover: "oklch(0.41 0.10 34)"
  primary-oxblood-active: "oklch(0.37 0.095 34)"
  primary-fg: "oklch(0.99 0.006 60)"
  primary-tint: "oklch(0.955 0.02 34)"
  accent-brass: "oklch(0.66 0.09 78)"
  accent-brass-ink: "oklch(0.50 0.09 72)"
  accent-tint: "oklch(0.955 0.03 82)"
  error: "oklch(0.53 0.20 27)"
  error-tint: "oklch(0.955 0.025 28)"
  warning: "oklch(0.52 0.13 60)"
  warning-tint: "oklch(0.96 0.04 75)"
  success: "oklch(0.50 0.11 150)"
  success-tint: "oklch(0.955 0.03 150)"
  info: "oklch(0.50 0.09 235)"
  info-tint: "oklch(0.955 0.025 235)"
  ring: "oklch(0.55 0.13 36)"
typography:
  display:
    fontFamily: "'IBM Plex Sans', ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.625rem"
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "-0.01em"
  headline:
    fontFamily: "'IBM Plex Sans', ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.3125rem"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "-0.005em"
  title:
    fontFamily: "'IBM Plex Sans', ui-sans-serif, system-ui, sans-serif"
    fontSize: "1.0625rem"
    fontWeight: 600
    lineHeight: 1.35
    letterSpacing: "normal"
  body:
    fontFamily: "'IBM Plex Sans', ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "normal"
  data:
    fontFamily: "'IBM Plex Mono', ui-monospace, 'SFMono-Regular', Menlo, monospace"
    fontSize: "0.8125rem"
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "normal"
    fontFeature: "'tnum' 1"
  label:
    fontFamily: "'IBM Plex Sans', ui-sans-serif, system-ui, sans-serif"
    fontSize: "0.6875rem"
    fontWeight: 500
    lineHeight: 1.2
    letterSpacing: "0.06em"
rounded:
  sm: "5px"
  md: "8px"
  lg: "12px"
  pill: "9999px"
spacing:
  "2xs": "2px"
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
  "2xl": "32px"
  "3xl": "48px"
components:
  button-primary:
    backgroundColor: "{colors.primary-oxblood}"
    textColor: "{colors.primary-fg}"
    rounded: "{rounded.sm}"
    padding: "8px 16px"
    typography: "{typography.body}"
  button-primary-hover:
    backgroundColor: "{colors.primary-oxblood-hover}"
    textColor: "{colors.primary-fg}"
  button-primary-active:
    backgroundColor: "{colors.primary-oxblood-active}"
    textColor: "{colors.primary-fg}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "8px 16px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "8px 12px"
  button-download-pdf:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.primary-oxblood}"
    rounded: "{rounded.sm}"
    padding: "6px 10px"
    typography: "{typography.body}"
  input:
    backgroundColor: "{colors.bg}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "8px 12px"
    height: "38px"
  select:
    backgroundColor: "{colors.bg}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "8px 12px"
    height: "38px"
  badge:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.muted}"
    rounded: "{rounded.pill}"
    padding: "2px 8px"
    typography: "{typography.label}"
  badge-status-live:
    backgroundColor: "{colors.success-tint}"
    textColor: "{colors.success}"
    rounded: "{rounded.pill}"
    padding: "2px 8px"
  table-header-cell:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.muted}"
    typography: "{typography.label}"
    padding: "8px 12px"
  table-cell:
    backgroundColor: "{colors.bg}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    padding: "8px 12px"
  table-cell-data:
    backgroundColor: "{colors.bg}"
    textColor: "{colors.ink}"
    typography: "{typography.data}"
    padding: "8px 12px"
  dropdown-menu:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "4px"
  group-header:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "12px 16px"
    typography: "{typography.title}"
---

# Design System: Busca Transparência Goiás

**Direção.** A identidade é **"O Códice"**: a ferramenta se apresenta como um código jurídico encadernado — couro *oxblood* na marca, um traço de latão dourado nos detalhes, dados dispostos como um livro-razão sobre papel de qualidade. Abandona por completo o azul-shadcn genérico (rejeitado) e a estética "SaaS de IA"; no lugar entra uma paleta institucional quente e incomum — bordô-terracota + latão sobre branco puro — que sinaliza gravidade jurídica e artesania sem virar decoração. A densidade é uma virtude: tabelas escaneáveis, colunas de identificadores (CNPJ, valor, data, nº) em monoespaçada com algarismos tabulares, e o refinamento vive nos estados (hover, foco, skeleton, vazio) — não em enfeite. Tema claro é o padrão (jurista lendo documentos sob luz de expediente em tela grande); o escuro é irmão completo para plantão e baixa luz.

## 1. Overview

**Creative North Star: "O Códice"**

Pense na estante de um gabinete: os códigos comentados encadernados em couro *oxblood*, o título gravado em latão na lombada, o papel espesso e as colunas de artigos alinhadas como um livro-razão. Este sistema traduz esse objeto para a tela. A cor da marca é o couro — um bordô-terracota grave, nunca um vermelho de alarme. O latão é o detalhe raro: um filete sob a marca, o selo de "fonte oficial", o sublinhado da aba ativa. Tudo o mais é papel e tinta: branco puro, texto quase-preto quente, filetes finos. A personalidade é **profissional, premium, inteligente** — sóbria sem ser burocrática, com o acabamento de um instrumento bem feito.

A densidade serve à análise. O usuário é um assessor jurídico varrendo licitações, contratos e legislação de seis municípios e baixando PDFs; a interface existe para **completar a pesquisa em poucos gestos e sumir na tarefa**. Por isso a tabela é o herói, não um grid de cards; as colunas numéricas viram uma "coluna-razão" monoespaçada e tabular que se lê como uma planilha oficial; e cada estado (carregando, vazio, erro) é desenhado para ensinar o próximo gesto, não para preencher espaço. Nada é inventado: quando um dado não existe, a célula degrada para "—", nunca para número fabricado.

O que este sistema **rejeita explicitamente** (âncoras do PRODUCT.md): a "cara de IA" — scaffolding-padrão de grids de cards idênticos, *eyebrow* em toda seção, gradientes decorativos, hero-metric com ícone+número, side-stripe borders. E rejeita o reflexo de primeira ordem "portal de governo = azul" e o de segunda ordem "então vira editorial-serifado": a resposta é uma paleta institucional quente (oxblood + latão) com uma sans de engenharia (IBM Plex), não mais um clichê.

**Key Characteristics:**
- **Oxblood, não azul.** Uma única cor de marca grave carrega ações e seleção; ≤10% de qualquer tela.
- **Coluna-razão.** Identificadores (CNPJ, valor, data, nº) em IBM Plex Mono com `tnum`, alinhados à direita.
- **Papel puro.** Fundo branco literal `oklch(1 0 0)`; a cor mora na marca e na tipografia, nunca no fundo.
- **Latão raro.** O dourado é assinatura, não paleta: filetes, selo de fonte, aba ativa.
- **Estados completos.** Todo controle tem default/hover/focus/active/disabled/loading/error; skeleton no lugar de spinner.
- **Densidade legível.** Escala rem fixa (ratio ~1.2), filetes finos, zebra por hover — não por listras fixas.

**Escalas de apoio** (detalhe nos tokens do frontmatter):
- **Espaçamento** — grade de 4px: `2xs 2px · xs 4px · sm 8px · md 12px · lg 16px · xl 24px · 2xl 32px · 3xl 48px`. Varie o ritmo; não use um único gutter uniforme.
- **Raios** — instrumento preciso, raio contido: `sm 5px` (controles, badges), `md 8px` (cards/painéis), `lg 12px` (dialogs/popovers), `pill 9999px` (só status dots e pills).
- **Z-index semântico** — `dropdown 1000 · sticky 1100` (cabeçalho de tabela e toolbar) `· backdrop 1200 · dialog 1300 · toast 1400 · tooltip 1500`. Nunca 999/9999.
- **Motion** — 150–250ms, sempre *ease-out*, só para estado/feedback. Tokens: `--dur-fast 120ms` (cor de hover/foco), `--dur-base 180ms` (maioria das transições), `--dur-slow 240ms` (entrada de dropdown/dialog, pulso de skeleton). Curvas: `--ease-out: cubic-bezier(0.16, 1, 0.3, 1)` (entradas), `--ease-standard: cubic-bezier(0.4, 0, 0.2, 1)` (troca simples). **`prefers-reduced-motion: reduce` é obrigatório** em toda animação: substitua deslocamento/escala por crossfade de opacidade ou transição instantânea; o pulso de skeleton vira opacidade estática.
- **Responsivo** — estrutural, não tipográfico. Desktop é o alvo (juristas no expediente); abaixo de `lg (1024px)` o formulário de busca colapsa de linha para empilhado e a tabela ganha *scroll* horizontal com a coluna `titulo` fixada (`position: sticky; left: 0`). A escala tipográfica **não** encolhe por viewport.

## 2. Colors

Paleta **Restrained**: neutros de papel levemente quentes, uma cor de marca oxblood que carrega ação e seleção, latão como assinatura rara, e semânticos funcionais (error/warning/success/info) que só aparecem no próprio estado. Todos os pares de texto foram verificados ≥4.5:1 em ambos os temas; contornos de controle ≥3:1 (WCAG 2.2 não-textual).

### Primary
- **Oxblood Institucional** (`oklch(0.47 0.108 36)`): o couro do códice. A única cor de marca — botão primário (com texto `primary-fg`), links, aba/linha selecionada, base do anel de foco. Grave e quente, nunca um vermelho vivo: o tom de "carimbo oficial e lombada de código", não de alarme. `hover` escurece para `oklch(0.41 0.10 34)`, `active` para `oklch(0.37 0.095 34)`. Fundo suave para seleção/badge: `primary-tint oklch(0.955 0.02 34)`.

### Secondary
- **Latão / Brass** (`oklch(0.66 0.09 78)`): o dourado gravado. Uso **raro e de assinatura** — filete sob a marca no header, selo/ícone de "fonte oficial", sublinhado da aba ativa. Como texto/rótulo em fundo claro use a variante escura **Brass Ink** (`oklch(0.50 0.09 72)`, 6.1:1). Fundo suave `accent-tint oklch(0.955 0.03 82)`. Nunca vira preenchimento de badge de status (colide com warning) nem decoração de seção.

### Neutral
- **Papel** (`bg oklch(1 0 0)`): branco puro literal. Fundo do conteúdo e do corpo da tabela. A cor mora na marca, não aqui.
- **Superfície** (`surface oklch(0.985 0.005 40)`): off-white de papel, quentíssimo. Painel do formulário de busca, cards, cabeçalho de tabela, toolbar — a segunda camada neutra do registro produto.
- **Superfície-2** (`surface-2 oklch(0.962 0.006 40)`): hover de linha da tabela, fundo de campo desabilitado, painel mais fundo.
- **Filete** (`border oklch(0.892 0.007 40)`): divisórias finas de 1px, gridlines da tabela, borda de card.
- **Filete Interativo** (`border-interactive oklch(0.64 0.012 40)`, 3.4:1): contorno de input/select/botão-secundário em repouso — atende contraste não-textual.
- **Tinta** (`ink oklch(0.26 0.014 38)`, 15.6:1): texto de corpo, cabeçalhos, dados. Quase-preto com calor de tinta, não preto puro.
- **Tinta Fraca** (`muted oklch(0.475 0.012 40)`, 6.7:1): texto secundário, rótulos de coluna, placeholder, meta, timestamps. **Também atende ≥4.5:1** — placeholder nunca é cinza-elegante ilegível.

### Semantic
- **Erro** (`error oklch(0.53 0.20 27)`, 5.9:1): mensagem/borda de erro, ação destrutiva. Distinto do oxblood por ser **mais claro e muito mais saturado** — lê-se como alerta vivo, não como marca. Fundo `error-tint oklch(0.955 0.025 28)`.
- **Aviso** (`warning oklch(0.52 0.13 60)`, 5.7:1): âmbar de atenção (ex.: "dados podem estar incompletos"). Fundo `warning-tint oklch(0.96 0.04 75)`.
- **Sucesso** (`success oklch(0.50 0.11 150)`, 5.7:1): confirmação, status "ao vivo/atualizado". Fundo `success-tint oklch(0.955 0.03 150)`.
- **Info** (`info oklch(0.50 0.09 235)`, 5.9:1): dica neutra, "resultado em cache". Fundo `info-tint oklch(0.955 0.025 235)`. É o **único** azul do sistema e nunca é cor de marca.
- **Anel de foco** (`ring oklch(0.55 0.13 36)`, 5.2:1): oxblood mais vivo, sempre 2px com `outline-offset: 2px`.

### Tema escuro (irmão completo — cena: plantão à noite, baixa luz, mesma tela)

Bloco `.dark` normativo. Não é duplicação do claro: são os valores escuros, que não têm outro lugar no frontmatter.

```css
:root {
  --bg: oklch(1 0 0);
  --surface: oklch(0.985 0.005 40);
  --surface-2: oklch(0.962 0.006 40);
  --border: oklch(0.892 0.007 40);
  --border-interactive: oklch(0.64 0.012 40);
  --ink: oklch(0.26 0.014 38);
  --muted: oklch(0.475 0.012 40);
  --primary: oklch(0.47 0.108 36);
  --primary-hover: oklch(0.41 0.10 34);
  --primary-active: oklch(0.37 0.095 34);
  --primary-fg: oklch(0.99 0.006 60);
  --primary-tint: oklch(0.955 0.02 34);
  --accent: oklch(0.66 0.09 78);
  --accent-ink: oklch(0.50 0.09 72);
  --accent-tint: oklch(0.955 0.03 82);
  --error: oklch(0.53 0.20 27);
  --error-tint: oklch(0.955 0.025 28);
  --warning: oklch(0.52 0.13 60);
  --warning-tint: oklch(0.96 0.04 75);
  --success: oklch(0.50 0.11 150);
  --success-tint: oklch(0.955 0.03 150);
  --info: oklch(0.50 0.09 235);
  --info-tint: oklch(0.955 0.025 235);
  --ring: oklch(0.55 0.13 36);
}

.dark {
  --bg: oklch(0.165 0.006 40);          /* carvão quente, não preto puro */
  --surface: oklch(0.205 0.007 40);
  --surface-2: oklch(0.245 0.008 40);
  --border: oklch(0.30 0.008 40);
  --border-interactive: oklch(0.50 0.012 40);   /* 3.2:1 vs bg */
  --ink: oklch(0.94 0.006 60);          /* 16.2:1 */
  --muted: oklch(0.72 0.008 50);        /* 7.8:1 */
  --primary: oklch(0.62 0.14 38);       /* terracota mais clara p/ contraste; texto branco */
  --primary-hover: oklch(0.68 0.145 38);
  --primary-active: oklch(0.58 0.135 38);
  --primary-fg: oklch(0.16 0.02 40);    /* 5.0:1 sobre primary */
  --primary-tint: oklch(0.30 0.05 34);  /* fundo de linha selecionada */
  --link: oklch(0.74 0.12 42);          /* 8.0:1 — oxblood não passa como texto no escuro; use este p/ links */
  --accent: oklch(0.72 0.10 80);
  --accent-ink: oklch(0.78 0.10 80);    /* 9.6:1 */
  --accent-tint: oklch(0.30 0.04 82);
  --error: oklch(0.70 0.16 28);         /* 6.7:1 */
  --error-tint: oklch(0.28 0.06 28);
  --warning: oklch(0.78 0.13 70);       /* 9.4:1 */
  --warning-tint: oklch(0.30 0.05 70);
  --success: oklch(0.72 0.12 152);      /* 8.2:1 */
  --success-tint: oklch(0.28 0.04 152);
  --info: oklch(0.72 0.10 232);         /* 7.9:1 */
  --info-tint: oklch(0.28 0.04 232);
  --ring: oklch(0.70 0.13 40);          /* 6.9:1 */
}
```

**Pares críticos verificados** (checker OKLCH→sRGB→WCAG). Claro: ink/bg 15.6 · muted/bg 6.7 · primary-fg/primary 7.0 · primary/bg 7.2 · error/bg 5.9 · warning/bg 5.7 · success/bg 5.7 · info/bg 5.9 · border-interactive/bg 3.4. Escuro: ink/bg 16.2 · muted/bg 7.8 · primary-fg/primary 5.0 · link/bg 8.0 · error/bg 6.7 · warning/bg 9.4 · success/bg 8.2 · info/bg 7.9 · border-interactive/bg 3.2.

### Named Rules
**A Regra da Voz Única.** O oxblood ocupa ≤10% de qualquer tela — botão primário, seleção, links, foco. Sua raridade é o que o torna *premium*; um oxblood em toda borda vira ruído.

**A Regra do Latão Raro.** O dourado nunca é uma "cor de UI". Aparece em no máximo dois lugares por tela (filete da marca + selo/aba). Se você está preenchendo um badge de status com latão, está errado — use o tint semântico.

**A Regra do "—".** Célula sem dado é `muted` "—". Nunca zero fabricado, nunca placeholder inventado. A confiança vem da fonte.

## 3. Typography

**Display/UI Font:** IBM Plex Sans (fallback `ui-sans-serif, system-ui, sans-serif`)
**Data/Mono Font:** IBM Plex Mono (fallback `ui-monospace, 'SFMono-Regular', Menlo, monospace`)

**Character:** Uma sans de engenharia, institucional e séria — legível em alta densidade, com algarismos tabulares excelentes. Substitui a DM Sans (default, sem voz). O par não é "duas sans parecidas": são **irmãs da mesma superfamília** (Plex Sans + Plex Mono), o que dá coerência e transforma a monoespaçada nas colunas de identificadores numa assinatura de "livro-razão oficial", não numa fonte de código à toa. Pesos: 400 (corpo/dados), 500 (rótulos, cabeçalho de tabela, badge), 600 (títulos e botões).

### Hierarchy
Escala rem **fixa** (não fluida), ratio ~1.2. Steps: 11 · 12 · 13 · 15 · 17 · 21 · 26px.
- **Display** (600, `1.625rem`/26px, lh 1.25, ls -0.01em): título da página ("Busca Transparência"). Um por tela. `text-wrap: balance`.
- **Headline** (600, `1.3125rem`/21px, lh 1.3): título de sub-seção/painel.
- **Title** (600, `1.0625rem`/17px, lh 1.35): cabeçalho de card, header de grupo de resultados.
- **Body** (400, `0.9375rem`/15px, lh 1.5): texto de UI padrão, rótulos de formulário, texto de botão, células de tabela alfabéticas. Prosa longa limitada a 65–75ch; tabela pode correr a 120ch+.
- **Data** (400 mono, `0.8125rem`/13px, lh 1.4, `font-variant-numeric: tabular-nums`): a **coluna-razão** — CNPJ, valor, data, nº do processo/contrato. Alinhada à direita quando numérica; à esquerda quando identificador textual (CNPJ).
- **Label** (500, `0.6875rem`/11px, ls +0.06em, MAIÚSCULAS): rótulo de grupo de coluna e micro-rótulo. **Uso escasso** — não é *eyebrow* de seção.

### Named Rules
**A Regra da Coluna-Razão.** Todo identificador (CNPJ, valor, data, nº) usa `data` (Plex Mono + `tnum`). Valores e datas alinham à direita; assim as ordens de grandeza empilham e o olho compara linha a linha como numa planilha oficial. Texto corrido nunca usa mono.

**A Regra do Rótulo Contido.** MAIÚSCULAS tracked (`label`) só rotulam grupos de coluna/dados. Colocá-las acima de cada seção reintroduz o *eyebrow* de IA — proibido.

## 4. Elevation

Sistema **plano por padrão, com camadas tonais**. A profundidade vem de contraste de superfície (`bg → surface → surface-2`) e filetes de 1px, não de sombra. Sombra existe só onde há **sobreposição real** (dropdown, dialog, toast) ou um leve *lift* de feedback no hover de elemento interativo. No tema escuro, a elevação se apoia em superfície mais clara + `border`, com sombra quase preta discreta; sombra colorida é proibida. A cor da sombra é um oxblood-neutro muito escuro, não preto puro — acabamento quente.

### Shadow Vocabulary
- **elev-0** (`box-shadow: none`): superfícies em repouso — painel de busca, card, linha de tabela. O default.
- **elev-1 — feedback** (`box-shadow: 0 1px 2px oklch(0.26 0.02 38 / 0.10)`): *lift* sutil no hover de botão/linha clicável e no botão de download focado.
- **elev-2 — overlay** (`box-shadow: 0 8px 24px -8px oklch(0.26 0.02 38 / 0.18)` + `border 1px`): dropdown de página/ações, popover, tooltip rico.
- **elev-3 — dialog** (`box-shadow: 0 24px 48px -16px oklch(0.26 0.02 38 / 0.28)` + `border 1px`): dialog modal (último recurso), sobre backdrop `oklch(0.26 0.02 38 / 0.40)`.

### Named Rules
**A Regra do Plano por Padrão.** Superfícies são planas em repouso. Sombra é resposta a estado (hover, overlay, foco), nunca decoração de card estático. Se um card tem sombra parado, remova-a.

**A Regra do Teste 2014.** Se parecer um app de 2014, a sombra está escura demais e o blur pequeno demais. Sombra de overlay é ampla, difusa e com *spread* negativo; nunca `0 2px 4px #000`.

## 5. Components

Vocabulário único em toda a tela: mesma forma de botão, mesmo controle de formulário, mesmo estilo de ícone (lucide, stroke 1.5–2px, 16–18px). Todo componente interativo especifica default/hover/focus-visible/active/disabled/loading/error. Foco sempre visível: `outline: 2px solid var(--ring); outline-offset: 2px`.

### Buttons
- **Forma:** raio `sm` (5px), altura 38px, padding `8px 16px`, peso 600, transição `background var(--dur-fast) var(--ease-standard)`.
- **Primary** (`button-primary`): fundo `primary-oxblood`, texto `primary-fg`. *hover* → `primary-oxblood-hover` + elev-1; *active* → `primary-oxblood-active`, sem lift; *focus-visible* → anel `ring`; *disabled* → `surface-2` + texto `muted`, `cursor: not-allowed`, sem hover; *loading* → spinner 16px `primary-fg` + rótulo, largura travada, `aria-busy`.
- **Secondary** (`button-secondary`): fundo `surface`, texto `ink`, borda `border-interactive`. *hover* → fundo `surface-2`; *active* → borda `ink`. Ação neutra (ex.: "Exportar CSV").
- **Ghost** (`button-ghost`): sem fundo/borda, texto `ink`, padding `8px 12px`. *hover* → fundo `surface-2`. Ações terciárias, ordenar coluna, ícones de toolbar.
- **Destructive:** fundo `error` + texto branco (só em confirmação real).

### Botão Baixar PDF (componente-assinatura)
A ação central do produto, em cada linha de resultado. **Não** é o botão primário oxblood — é um controle compacto de baixo peso que não compete com a leitura da tabela.
- **Estilo:** `button-download-pdf` — fundo `surface`, texto/ícone `primary-oxblood`, borda `border`, raio `sm`, padding `6px 10px`, ícone de documento (16px) + "PDF" em `body`.
- **Estados:** *default* discreto; *hover* → fundo `primary-tint`, borda `primary-oxblood`, elev-1; *focus-visible* → anel `ring`; *loading* → ícone vira spinner, texto "Baixando…", `aria-busy`, controle desabilitado; *indisponível* → texto `muted` "—" com tooltip "PDF não disponível na fonte" (nunca botão morto sem explicação); *error* → ícone de alerta `error` + tooltip com a mensagem, retry no mesmo controle.

### Inputs / Selects (formulário de busca)
Município, Seção, Ano, CNPJ.
- **Estilo:** `input`/`select` — fundo `bg`, texto `ink`, borda `border-interactive`, raio `sm`, altura 38px, padding `8px 12px`. Placeholder em `muted` (≥4.5:1).
- **Estados:** *hover* → borda `ink`; *focus-visible* → borda `ring` + anel 2px, transição `var(--dur-fast)`; *filled* → texto `ink` cheio; *disabled* → fundo `surface-2`, texto `muted`, `cursor: not-allowed`; *error* → borda `error` + texto de ajuda `error` abaixo (`role="alert"`); Select desabilitado enquanto o município não é escolhido (Seção depende de Município) mostra placeholder "Escolha um município primeiro".
- **Rótulo:** `body` peso 500 acima do campo, associado por `htmlFor`. Nunca placeholder-como-rótulo.

### Badges / Pills
Estilo **soft-tint** (fundo tint + texto do mesmo matiz), nunca preenchimento saturado com texto branco.
- **Município / Seção** (`badge`): fundo `surface-2`, texto `muted`, `pill`, `label`. Neutro — os seis municípios **não** viram arco-íris de cores.
- **Status "ao vivo/atualizado"** (`badge-status-live`): fundo `success-tint`, texto `success`, com dot 6px.
- **Status "em cache"**: fundo `info-tint`, texto `info`.
- **Contagem** (ex.: "24 resultados"): fundo `surface-2`, texto `ink`, `data` para o número.

### Tabela de resultados (herói)
- **Cabeçalho** (`table-header-cell`): fundo `surface`, texto `label` em `muted`, `position: sticky; top: 0`, z `sticky`, filete inferior `border`. Colunas ordenáveis são `button-ghost` com ícone de seta (↑/↓/↕) 14px; a coluna ordenada mostra a seta em `ink`, as demais em `muted`.
- **Linhas** (`table-cell`): fundo `bg`, filete inferior `border` de 1px (**sem zebra fixa** — a separação é o filete). *hover* → fundo `surface-2` (transição `var(--dur-fast)`); *selecionada* → fundo `primary-tint` + filete-esquerdo? **não**: use fundo `primary-tint` inteiro, jamais side-stripe.
- **Células de dado** (`table-cell-data`): CNPJ/valor/data/nº em `data` (mono + `tnum`); valor e data à direita.
- **Paginação:** rodapé com "Mostrando X–Y de Z" (`muted`), controle de tamanho de página (Select 10/25/50) e botões prev/next (`button-ghost`, disabled nos extremos).
- **Loading:** **skeleton de linhas** (8–10 linhas, blocos `surface-2` com pulso de opacidade `var(--dur-slow)`), preservando a largura das colunas — nunca spinner no meio do conteúdo.
- **Vazio (após busca):** ver Empty States.
- **Overflow:** `<lg` rola horizontalmente com a coluna `titulo` fixa (`sticky left:0`), sombra de borda ao rolar.
- **Semântica:** `<table>` real com `<thead>/<th scope="col">`, `<caption>` sr-only descrevendo a busca, `aria-sort` na coluna ordenada.

### Grupos de resultados (folha / legislação multi-fonte)
Cabeçalho de grupo (`group-header`): fundo `surface`, `title`, raio `md`, com nome da fonte + `badge` de contagem + selo de latão "fonte oficial" (link ao portal). Colapsável via `<details>`/`<summary>` nativo ou botão com `aria-expanded`; chevron 16px gira 180° em `var(--dur-base) var(--ease-standard)`. Conteúdo é a tabela acima. Sem cards aninhados.

### Dropdown / Menu
`dropdown-menu`: fundo `surface`, raio `md`, elev-2, padding 4px; itens `body` com padding `8px 12px`, *hover* → `surface-2`, item ativo com check `primary-oxblood`. Renderizar via portal/popover para escapar de `overflow` da tabela (não `position:absolute` dentro de container com scroll). z `dropdown`.

### Navegação — Header / Footer / Theme toggle
- **Header:** faixa `surface`, altura ~56px, wordmark "Busca Transparência **Goiás**" (Goiás em `ink`, resto `muted`) com **filete de latão** de 2px sob a marca (a única gravação dourada persistente). À direita: theme toggle. Filete inferior `border`.
- **Footer:** `muted`, `caption`, link "dados direto da fonte oficial NucleoGov"; sem grid de colunas decorativo.
- **Theme toggle:** `button-ghost` com ícone sol/lua 18px; troca de tema em crossfade `var(--dur-base)`; `aria-pressed`; respeita `prefers-color-scheme` no primeiro carregamento.

### Empty & Error states
- **Empty inicial (antes de buscar):** ensina a interface — título `title` "Comece uma busca", texto `body`/`muted` "Escolha um município e uma seção; refine por ano ou CNPJ." Sem ilustração genérica; opcionalmente o ícone de documento em `muted`.
- **Empty pós-busca (0 resultados):** "Nenhum resultado para estes filtros" + sugestão acionável ("remova o filtro de ano" / "verifique o CNPJ") como `button-ghost`. Nunca só "nada aqui".
- **Error:** bloco `error-tint` com borda `error` (borda **completa**, não side-stripe), ícone de alerta `error`, título `title`, mensagem exata da falha em `body`, e botão "Tentar de novo" (`button-secondary`). Falha degrada com transparência: mostra o que carregou + o erro parcial, nunca tela branca.

## 6. Do's and Don'ts

### Do:
- **Do** usar oxblood (`oklch(0.47 0.108 36)`) como única cor de marca, em ≤10% da tela — botão primário, seleção, links, foco (Regra da Voz Única).
- **Do** manter o fundo branco puro `oklch(1 0 0)` no claro e carvão quente `oklch(0.165 0.006 40)` no escuro; a cor mora na marca e na tipografia, nunca no fundo.
- **Do** renderizar CNPJ/valor/data/nº em IBM Plex Mono com `tabular-nums`, valores e datas alinhados à direita (Regra da Coluna-Razão).
- **Do** cobrir todos os estados de cada controle (default/hover/focus/active/disabled/loading/error) e usar **skeleton** de linhas no carregamento, não spinner no meio do conteúdo.
- **Do** verificar contraste ≥4.5:1 para todo texto (inclusive placeholder) e ≥3:1 para contornos de controle, em claro e escuro.
- **Do** desenhar empty states que ensinam o próximo gesto e error states com borda completa + mensagem exata + retry.
- **Do** respeitar `prefers-reduced-motion: reduce` em toda animação (crossfade/instantâneo) e manter transições em 150–250ms ease-out.
- **Do** degradar dado ausente para `muted` "—" (Regra do "—"), nunca inventar número.

### Don't:
- **Don't** usar azul-shadcn default (`#3b82f6` / `hsl(221 83% 53%)`) como marca — **rejeitado**. O único azul do sistema é o `info` semântico.
- **Don't** cair na "cara de IA": nada de grid de cards idênticos (ícone+heading+texto), nada de *eyebrow* MAIÚSCULO tracked acima de cada seção, nada de marcadores numerados 01/02/03 como scaffolding.
- **Don't** usar hero-metric (número grande + rótulo pequeno + stats + gradiente) — clichê SaaS proibido.
- **Don't** usar `border-left`/`border-right` > 1px como listra colorida em linha, card ou alerta (side-stripe) — use borda completa, fundo tint ou nada.
- **Don't** usar gradiente em texto (`background-clip: text`), gradientes decorativos, nem glassmorphism default.
- **Don't** colorir os seis municípios como arco-íris de badges; município/seção são `badge` neutros soft-tint.
- **Don't** preencher badge de status com latão (colide com warning) nem usar latão como cor de UI — é assinatura rara (Regra do Latão Raro).
- **Don't** pôr sombra em card estático (Regra do Plano por Padrão); sombra só em overlay/hover/foco.
- **Don't** usar fonte display/serifada em rótulos, botões ou dados; nem reinventar controles-padrão (scrollbar custom, modal como primeira opção, select exótico).
- **Don't** deixar cinza-claro "elegante" ilegível em texto secundário/placeholder — `muted` é aferido para ≥4.5:1.
