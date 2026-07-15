"use client";

import { useMemo, useState } from "react";
import { ArrowUp, ArrowDown, ArrowUpDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import type { ItemTransparencia } from "@/lib/api-types";

interface Props {
  items: ItemTransparencia[];
  sourceUrl?: string;
  cached?: boolean;
}

const PAGE_SIZES = [10, 25, 50] as const;
const RIGHT_ALIGN_COLS = new Set(["data", "valor", "numero"]);
const MONO_COLS = new Set(["data", "valor", "cnpj", "numero"]);

function detectColumns(items: ItemTransparencia[]): string[] {
  // Colunas: união ordenada das chaves; titulo/link/data/valor primeiro.
  // Só entra a coluna que tem valor exibível em ALGUMA linha: uma coluna 100%
  // vazia (ex.: `raw`, sempre objeto → "—"; ou `valor` quando o portal não
  // expõe o campo na lista) vira só ruído de traços na tabela-razão.
  const order = ["titulo", "data", "valor", "credor", "cnpj", "modalidade", "numero", "link"];
  const renderable = (k: string) => items.some((it) => cellToString(it[k]) !== "");
  const seen = new Set<string>();
  const cols: string[] = [];
  for (const k of order) {
    if (renderable(k)) {
      cols.push(k);
      seen.add(k);
    }
  }
  for (const it of items) {
    for (const k of Object.keys(it)) {
      if (!seen.has(k) && renderable(k)) {
        cols.push(k);
        seen.add(k);
      }
    }
  }
  return cols;
}

export function toCsv(items: ItemTransparencia[], cols: string[]): string {
  const escape = (v: unknown): string => {
    const s = cellToString(v);
    if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
    return s;
  };
  const header = cols.map(escape).join(",");
  const rows = items.map((it) => cols.map((c) => escape(it[c])).join(","));
  return [header, ...rows].join("\n");
}

function download(filename: string, content: string) {
  const blob = new Blob([content], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function ResultadoTable({ items, sourceUrl, cached }: Props) {
  const cols = useMemo(() => detectColumns(items), [items]);
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState<(typeof PAGE_SIZES)[number]>(25);

  const sorted = useMemo(() => {
    if (!sortKey) return items;
    const copy = [...items];
    copy.sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      const an = Number(av);
      const bn = Number(bv);
      const numeric = Number.isFinite(an) && Number.isFinite(bn);
      if (numeric) return sortDir === "asc" ? an - bn : bn - an;
      const as = String(av ?? "");
      const bs = String(bv ?? "");
      return sortDir === "asc" ? as.localeCompare(bs) : bs.localeCompare(as);
    });
    return copy;
  }, [items, sortKey, sortDir]);

  const totalPages = Math.max(1, Math.ceil(sorted.length / pageSize));
  const visible = sorted.slice(page * pageSize, (page + 1) * pageSize);

  function onSort(key: string) {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  function onExport() {
    const csv = toCsv(sorted, cols);
    download(`busca-transparencia-${Date.now()}.csv`, csv);
  }

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3 text-[0.9375rem] text-muted-foreground">
          <span>
            <span className="font-mono tabular-nums text-foreground">{sorted.length}</span>{" "}
            {sorted.length === 1 ? "resultado" : "resultados"}
          </span>
          {cached !== undefined && (
            <Badge variant={cached ? "info" : "success"} dot>
              {cached ? "em cache" : "atualizado"}
            </Badge>
          )}
          {sourceUrl && (
            <a
              href={sourceUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary underline underline-offset-2 hover:text-primary-hover"
            >
              fonte
            </a>
          )}
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <span>Linhas:</span>
            <Select
              value={String(pageSize)}
              onChange={(e) => {
                setPageSize(Number(e.target.value) as (typeof PAGE_SIZES)[number]);
                setPage(0);
              }}
              options={PAGE_SIZES.map((n) => ({ value: String(n), label: String(n) }))}
              className="!h-8 w-20 pr-7 text-xs"
            />
          </label>
          <Button type="button" variant="secondary" size="sm" onClick={onExport}>
            Exportar CSV
          </Button>
        </div>
      </div>

      <Table>
        <caption className="sr-only">
          Resultados da busca ({sorted.length} itens, página {page + 1} de {totalPages})
        </caption>
        <THead>
          <TR className="hover:bg-card">
            {cols.map((c, i) => {
              const active = sortKey === c;
              return (
                <TH key={c} stickyLeft={i === 0} aria-sort={active ? (sortDir === "asc" ? "ascending" : "descending") : "none"}>
                  <button
                    type="button"
                    onClick={() => onSort(c)}
                    className={cn(
                      "inline-flex items-center gap-1 uppercase tracking-[0.06em] transition-colors duration-[var(--dur-fast)] ease-[var(--ease-standard)] hover:text-foreground",
                      active && "text-foreground",
                    )}
                    aria-label={`Ordenar por ${c}`}
                  >
                    {c}
                    {active ? (
                      sortDir === "asc" ? (
                        <ArrowUp className="h-3.5 w-3.5" aria-hidden="true" />
                      ) : (
                        <ArrowDown className="h-3.5 w-3.5" aria-hidden="true" />
                      )
                    ) : (
                      <ArrowUpDown className="h-3.5 w-3.5 opacity-40" aria-hidden="true" />
                    )}
                  </button>
                </TH>
              );
            })}
          </TR>
        </THead>
        <TBody>
          {visible.map((it, i) => (
            <TR key={`${page}-${i}`}>
              {cols.map((c, ci) => (
                <TD
                  key={c}
                  stickyLeft={ci === 0}
                  className={cn(
                    MONO_COLS.has(c) && "font-mono tabular-nums",
                    RIGHT_ALIGN_COLS.has(c) && "text-right",
                  )}
                >
                  {renderCell(c, it[c])}
                </TD>
              ))}
            </TR>
          ))}
        </TBody>
      </Table>

      {totalPages > 1 && (
        <nav
          aria-label="Paginação"
          className="mt-3 flex items-center justify-between text-[0.9375rem]"
        >
          <span className="text-muted-foreground">
            Mostrando {page * pageSize + 1}–{Math.min((page + 1) * pageSize, sorted.length)} de{" "}
            <span className="font-mono tabular-nums">{sorted.length}</span>
          </span>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
            >
              Anterior
            </Button>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
            >
              Próxima
            </Button>
          </div>
        </nav>
      )}
    </div>
  );
}

// Objetos (ex.: coluna "raw") não têm representação tabular sensata: viram
// vazio tanto na célula exibida quanto no CSV exportado (mesma regra, uma função).
function cellToString(value: unknown): string {
  if (value == null || value === "" || typeof value === "object") return "";
  return String(value);
}

function renderCell(col: string, value: unknown) {
  const s = cellToString(value);
  if (s === "") return <span className="text-muted-foreground">—</span>;
  if (col === "link") {
    return (
      <a
        href={s}
        target="_blank"
        rel="noopener noreferrer"
        className="text-primary underline underline-offset-2 hover:text-primary-hover"
      >
        abrir
      </a>
    );
  }
  return s;
}
