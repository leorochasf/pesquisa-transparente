/** Renderer markdown mínimo do relatório do caso (plano §7, W0-F4). Cobre só
 *  o subconjunto que `busca_go/nucleo/relatorio.py` emite de fato:
 *  `#`/`##`/`###`, parágrafos, listas `-`, links `[texto](url)`, tabelas
 *  simples (pipe), e inline `**negrito**`/`` `código` ``/`_itálico_`. Saída
 *  são nós React (via `React.createElement`, sem JSX) — nunca HTML injetado,
 *  o texto é sempre escapado pelo próprio React. O literal `[não verificado]`
 *  é realçado em `warning` mesmo dentro de negrito. */

import * as React from "react";

type Block =
  | { type: "heading"; level: 1 | 2 | 3; text: string }
  | { type: "paragraph"; text: string }
  | { type: "list"; items: string[] }
  | { type: "table"; header: string[]; rows: string[][] };

const NAO_VERIFICADO = "[não verificado]";

function splitTableRow(line: string): string[] {
  const trimmed = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  return trimmed.split("|").map((c) => c.trim());
}

const SEPARATOR_ROW = /^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?$/;

export function parseMarkdownMin(md: string): Block[] {
  const lines = md.split("\n");
  const blocks: Block[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    if (line.trim() === "") {
      i++;
      continue;
    }

    const heading = /^(#{1,3})\s+(.*)$/.exec(line);
    if (heading) {
      blocks.push({ type: "heading", level: heading[1].length as 1 | 2 | 3, text: heading[2] });
      i++;
      continue;
    }

    if (/^\|.*\|$/.test(line.trim())) {
      const header = splitTableRow(line);
      i++;
      if (i < lines.length && SEPARATOR_ROW.test(lines[i].trim())) {
        i++;
      }
      const rows: string[][] = [];
      while (i < lines.length && /^\|.*\|$/.test(lines[i].trim())) {
        rows.push(splitTableRow(lines[i]));
        i++;
      }
      blocks.push({ type: "table", header, rows });
      continue;
    }

    if (/^-\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^-\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^-\s+/, ""));
        i++;
      }
      blocks.push({ type: "list", items });
      continue;
    }

    const paraLines: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !/^#{1,3}\s/.test(lines[i]) &&
      !/^-\s+/.test(lines[i]) &&
      !/^\|.*\|$/.test(lines[i].trim())
    ) {
      paraLines.push(lines[i]);
      i++;
    }
    blocks.push({ type: "paragraph", text: paraLines.join(" ") });
  }

  return blocks;
}

function renderPlainWithWarning(text: string, keyPrefix: string): React.ReactNode[] {
  const parts = text.split(/(\[não verificado\])/g).filter((p) => p !== "");
  return parts.map((p, i) =>
    p === NAO_VERIFICADO
      ? React.createElement(
          "span",
          { key: `${keyPrefix}-w${i}`, className: "font-medium text-warning" },
          p,
        )
      : p,
  );
}

// W3-F1: `_([^_]+)_` sem fronteira de palavra casava o `_` interno de tokens
// como `dano_erario_folha` (dois underscores) e engolia o miolo em <em> — a
// mesma guarda que o W1 aplicou no caminho do PDF (`relatorio.py`,
// `_ITALICO_INLINE_RE`), agora espelhada aqui.
const INLINE_PATTERN =
  /\[([^\]]+)\]\(([^)]+)\)|\*\*([\s\S]+?)\*\*|`([^`]+)`|(?<!\w)_([^_]+)_(?!\w)/;

/** W3-F2: o plano (§7, W0-F3) já decidiu não confiar em links relativos do
 *  markdown para download — só o índice estruturado (join com
 *  `caso.evidencias`) vira download vivo. Um link absoluto (`http(s)://` ou
 *  raiz `/…`) segue clicável; um relativo (`evidencias/…`) resolveria para
 *  uma rota inexistente do Next (404) — degrada para texto simples. */
function ehLinkAbsoluto(href: string): boolean {
  return /^https?:\/\//.test(href) || href.startsWith("/");
}

function parseInline(text: string, keyPrefix: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  let rest = text;
  let key = 0;

  while (rest.length > 0) {
    const m = INLINE_PATTERN.exec(rest);
    if (!m) {
      nodes.push(...renderPlainWithWarning(rest, `${keyPrefix}-${key++}`));
      break;
    }
    if (m.index > 0) {
      nodes.push(...renderPlainWithWarning(rest.slice(0, m.index), `${keyPrefix}-${key++}`));
    }
    if (m[1] !== undefined) {
      if (ehLinkAbsoluto(m[2])) {
        nodes.push(
          React.createElement(
            "a",
            {
              key: `${keyPrefix}-${key++}`,
              href: m[2],
              target: "_blank",
              rel: "noopener noreferrer",
              className: "text-primary underline underline-offset-2 hover:text-primary-hover",
            },
            m[1],
          ),
        );
      } else {
        nodes.push(...renderPlainWithWarning(`${m[1]} (${m[2]})`, `${keyPrefix}-${key++}`));
      }
    } else if (m[3] !== undefined) {
      nodes.push(
        React.createElement(
          "strong",
          {
            key: `${keyPrefix}-${key}`,
            className: m[3] === NAO_VERIFICADO ? "font-semibold text-warning" : "font-semibold",
          },
          ...parseInline(m[3], `${keyPrefix}-${key++}b`),
        ),
      );
    } else if (m[4] !== undefined) {
      nodes.push(
        React.createElement(
          "code",
          {
            key: `${keyPrefix}-${key++}`,
            className: "rounded-sm bg-muted px-1 py-0.5 font-mono text-[0.85em] tabular-nums",
          },
          m[4],
        ),
      );
    } else if (m[5] !== undefined) {
      nodes.push(React.createElement("em", { key: `${keyPrefix}-${key++}` }, m[5]));
    }
    rest = rest.slice(m.index + m[0].length);
  }

  return nodes;
}

const HEADING_CLASS: Record<1 | 2 | 3, string> = {
  1: "mt-6 text-[1.25rem] font-semibold leading-[1.3] first:mt-0",
  2: "mt-6 text-[1.0625rem] font-semibold leading-[1.35] first:mt-0",
  3: "mt-4 text-[0.9375rem] font-semibold leading-[1.4]",
};

export interface MarkdownMinOptions {
  /** Para a tabela "Índice de evidências" (coluna 1 = ev_id) — mapeia ev_id
   *  para a URL de download via proxy (W0-F3, plano §7). `null` = ev_id sem
   *  correspondência em `caso.evidencias` (defensivo — não deveria ocorrer). */
  linkEvidencia?: (evId: string) => string | null;
}

function renderTable(
  block: { header: string[]; rows: string[][] },
  blockKey: string,
  options?: MarkdownMinOptions,
): React.ReactNode {
  const ehIndiceEvidencias = block.header[0]?.trim() === "Evidência" && options?.linkEvidencia;

  return React.createElement(
    "div",
    { key: blockKey, className: "mt-4 w-full overflow-x-auto rounded-md border border-border" },
    React.createElement(
      "table",
      { className: "w-full border-collapse text-[0.9375rem]" },
      React.createElement(
        "thead",
        { className: "border-b border-border bg-card text-left" },
        React.createElement(
          "tr",
          null,
          ...block.header.map((h, ci) =>
            React.createElement(
              "th",
              {
                key: ci,
                scope: "col",
                className:
                  "px-3 py-2 text-[0.6875rem] font-medium uppercase leading-[1.2] tracking-[0.06em] text-muted-foreground",
              },
              h,
            ),
          ),
        ),
      ),
      React.createElement(
        "tbody",
        { className: "bg-background" },
        ...block.rows.map((row, ri) =>
          React.createElement(
            "tr",
            { key: ri, className: "border-b border-border last:border-0" },
            ...row.map((cell, ci) => {
              if (ehIndiceEvidencias && ci === 0) {
                const evId = cell.trim();
                const url = options!.linkEvidencia!(evId);
                return React.createElement(
                  "td",
                  { key: ci, className: "px-3 py-2 align-top font-mono tabular-nums" },
                  url
                    ? React.createElement(
                        "a",
                        {
                          href: url,
                          className:
                            "text-primary underline underline-offset-2 hover:text-primary-hover",
                        },
                        evId,
                      )
                    : evId,
                );
              }
              return React.createElement(
                "td",
                { key: ci, className: "px-3 py-2 align-top" },
                ...parseInline(cell, `${blockKey}-${ri}-${ci}`),
              );
            }),
          ),
        ),
      ),
    ),
  );
}

/** Converte o markdown do relatório em nós React. Nunca usa
 *  `dangerouslySetInnerHTML` — sem lib nova (plano §7 "Riscos e decisões"). */
export function renderMarkdownMin(md: string, options?: MarkdownMinOptions): React.ReactNode {
  const blocks = parseMarkdownMin(md);
  return blocks.map((block, i) => {
    const key = `b${i}`;
    switch (block.type) {
      case "heading":
        return React.createElement(
          block.level === 1 ? "h1" : block.level === 2 ? "h2" : "h3",
          { key, className: HEADING_CLASS[block.level] },
          ...parseInline(block.text, key),
        );
      case "paragraph":
        return React.createElement(
          "p",
          { key, className: "mt-2 text-[0.9375rem] leading-[1.6] text-foreground" },
          ...parseInline(block.text, key),
        );
      case "list":
        return React.createElement(
          "ul",
          { key, className: "mt-2 list-disc space-y-1 pl-5 text-[0.9375rem] text-foreground" },
          ...block.items.map((item, ii) =>
            React.createElement("li", { key: ii }, ...parseInline(item, `${key}-${ii}`)),
          ),
        );
      case "table":
        return renderTable(block, key, options);
      default:
        return null;
    }
  });
}
