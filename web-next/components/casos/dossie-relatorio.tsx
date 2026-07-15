"use client";

import * as React from "react";
import { Download, FileText, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/shared/error-state";
import { EmptyState } from "@/components/shared/empty-state";
import { Skeleton } from "@/components/shared/skeleton";
import { evidenciaArquivoUrl, obterRelatorioMd, relatorioUrl } from "@/lib/casos-api";
import { ApiError } from "@/lib/api";
import { renderMarkdownMin } from "@/lib/markdown-min";
import type { CasoDetalhe } from "@/lib/casos-types";

function downloadBlob(filename: string, blob: Blob) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

type PdfEstado = "idle" | "baixando" | "indisponivel" | "erro";

interface DossieRelatorioProps {
  caso: CasoDetalhe;
  /** Muda quando um job termina — força novo fetch do relatório (dados novos
   *  persistidos). */
  atualizarEm: number;
}

/** Seção 6 do dossiê (plano §1.2/§7): markdown do relatório renderizado sem
 *  HTML bruto (`lib/markdown-min.ts`) + baixar .md/.pdf. PDF em 501 degrada
 *  para "indisponível", sem quebrar a tela. */
export function DossieRelatorio({ caso, atualizarEm }: DossieRelatorioProps) {
  const [markdown, setMarkdown] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [erro, setErro] = React.useState<string | null>(null);
  const [pdfEstado, setPdfEstado] = React.useState<PdfEstado>("idle");
  const semRegistros = caso.itens.length === 0 && caso.evidencias.length === 0;

  const buscar = React.useCallback(() => {
    setLoading(true);
    setErro(null);
    obterRelatorioMd(caso.id)
      .then((md) => setMarkdown(md))
      .catch((e) => setErro(e instanceof ApiError ? e.message : "Não foi possível carregar o relatório."))
      .finally(() => setLoading(false));
  }, [caso.id]);

  React.useEffect(() => {
    if (semRegistros) {
      setLoading(false);
      return;
    }
    buscar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caso.id, atualizarEm, semRegistros]);

  function linkEvidencia(evId: string): string | null {
    const encontrada = caso.evidencias.find((e) => e.id === evId);
    return encontrada ? evidenciaArquivoUrl(caso.id, encontrada.id) : null;
  }

  function baixarMd() {
    if (!markdown) return;
    downloadBlob(`relatorio-${caso.id}.md`, new Blob([markdown], { type: "text/markdown;charset=utf-8;" }));
  }

  async function baixarPdf() {
    setPdfEstado("baixando");
    try {
      const res = await fetch(relatorioUrl(caso.id, "pdf"));
      if (res.status === 501) {
        setPdfEstado("indisponivel");
        return;
      }
      if (!res.ok) {
        setPdfEstado("erro");
        return;
      }
      const blob = await res.blob();
      downloadBlob(`relatorio-${caso.id}.pdf`, blob);
      setPdfEstado("idle");
    } catch {
      setPdfEstado("erro");
    }
  }

  return (
    <section aria-labelledby="dossie-relatorio-titulo">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="dossie-relatorio-titulo" className="text-[1.0625rem] font-semibold leading-[1.35]">
          Relatório
        </h2>
        {!semRegistros && markdown && (
          <div className="flex items-center gap-2">
            <Button type="button" variant="secondary" size="sm" onClick={baixarMd}>
              <Download className="h-3.5 w-3.5" aria-hidden="true" />
              Baixar .md
            </Button>
            {pdfEstado === "indisponivel" ? (
              <span
                className="text-[0.8125rem] text-muted-foreground"
                title="PDF não disponível na fonte"
              >
                Exportação em PDF ainda não disponível
              </span>
            ) : (
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={baixarPdf}
                loading={pdfEstado === "baixando"}
              >
                {pdfEstado === "baixando" ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                ) : (
                  <FileText className="h-3.5 w-3.5" aria-hidden="true" />
                )}
                Baixar PDF
              </Button>
            )}
          </div>
        )}
      </div>

      <div className="mt-3">
        {semRegistros ? (
          <EmptyState
            title="Nenhum registro ainda"
            description="Use “Investigar” para o assistente varrer, ou “Pesquisar registros” / “Coletar folha” para buscar você mesmo."
          />
        ) : loading ? (
          <div className="space-y-2 rounded-md border border-border bg-card p-4">
            <Skeleton className="h-4 w-1/3" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-2/3" />
          </div>
        ) : erro ? (
          <ErrorState title="Falha ao carregar o relatório" message={erro} onRetry={buscar} />
        ) : markdown ? (
          <div className="rounded-md border border-border bg-card p-5">
            {renderMarkdownMin(markdown, { linkEvidencia })}
          </div>
        ) : null}
        {pdfEstado === "erro" && (
          <p className="mt-2 text-[0.8125rem] text-destructive">
            Não foi possível baixar o PDF do relatório agora.
          </p>
        )}
      </div>
    </section>
  );
}
