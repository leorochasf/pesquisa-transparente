import { describe, expect, it } from "vitest";
import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { parseMarkdownMin, renderMarkdownMin } from "./markdown-min";

function renderInlineHtml(md: string): string {
  return renderToStaticMarkup(React.createElement(React.Fragment, null, renderMarkdownMin(md)));
}

describe("parseMarkdownMin — subconjunto emitido por relatorio.py (W0-F4)", () => {
  it("reconhece headings h1/h2/h3", () => {
    const blocks = parseMarkdownMin("# Dossiê — X\n\n## Síntese\n\n### Achado 1\n");
    expect(blocks).toEqual([
      { type: "heading", level: 1, text: "Dossiê — X" },
      { type: "heading", level: 2, text: "Síntese" },
      { type: "heading", level: 3, text: "Achado 1" },
    ]);
  });

  it("agrupa linhas de lista consecutivas em um único bloco", () => {
    const blocks = parseMarkdownMin("- Fornecedor: X\n- Documentos: ev_1\n");
    expect(blocks).toEqual([
      { type: "list", items: ["Fornecedor: X", "Documentos: ev_1"] },
    ]);
  });

  it("reconhece tabela pipe com cabeçalho + separador + linhas", () => {
    const md = "| Evidência | Tipo | sha256 |\n|---|---|---|\n| ev_1 | pdf | `abc123` |\n";
    const blocks = parseMarkdownMin(md);
    expect(blocks).toEqual([
      {
        type: "table",
        header: ["Evidência", "Tipo", "sha256"],
        rows: [["ev_1", "pdf", "`abc123`"]],
      },
    ]);
  });

  it("preserva o literal [não verificado] no texto do bloco (realce fica na renderização)", () => {
    const blocks = parseMarkdownMin("- Lastro: **[não verificado]** — sem evidência.\n");
    expect(blocks[0]).toEqual({
      type: "list",
      items: ["Lastro: **[não verificado]** — sem evidência."],
    });
  });
});

describe("parseInline — itálico e links (W3-F1/F2)", () => {
  it("W3-F1: não corrompe token com dois underscores (dano_erario_folha) — e itálico real continua funcionando", () => {
    const html = renderInlineHtml("Tipo: dano_erario_folha · Nota: _itálico real_.");
    expect(html).toContain("dano_erario_folha");
    expect(html).not.toContain("dano<em>erario</em>folha");
    expect(html).toContain("<em>itálico real</em>");
  });

  it("W3-F2: link absoluto (http/https ou raiz /) continua clicável", () => {
    const html = renderInlineHtml("[Documento](https://exemplo.gov.br/x.pdf) e [Rota](/casos/1).");
    expect(html).toContain('<a href="https://exemplo.gov.br/x.pdf"');
    expect(html).toContain('<a href="/casos/1"');
  });

  it("W3-F2: link relativo de evidência degrada para texto, nunca vira âncora morta", () => {
    const html = renderInlineHtml("[Folha JOANA](evidencias/senadorcanedo/folha/x.png)");
    expect(html).not.toContain("<a ");
    expect(html).toContain("Folha JOANA (evidencias/senadorcanedo/folha/x.png)");
  });
});
