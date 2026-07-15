import { Download } from "lucide-react";
import { evidenciaArquivoUrl } from "@/lib/casos-api";
import type { EvidenciaCaso } from "@/lib/casos-types";
import { cn } from "@/lib/utils";

/** `sha256` curto para a coluna-razão (8 chars, DESIGN.md §3 "Regra da
 *  Coluna-Razão") — exportado como função pura para ser testável sem DOM. */
export function shaCurto(sha256: string): string {
  return sha256.slice(0, 8);
}

interface LastroEvidenciaProps {
  casoId: string;
  evidencias: EvidenciaCaso[];
}

/** Célula de lastro (plano §1.2 seção 4 / §5 `casos/lastro-evidencia.tsx`):
 *  `ev_id` + `sha256` curto em coluna-razão mono, botão "Baixar" no estilo
 *  `button-download-pdf` por evidência. Sem evidência → `[não verificado]`
 *  em `warning`, nunca "—" silencioso (plano §6.1/§6.3). */
export function LastroEvidencia({ casoId, evidencias }: LastroEvidenciaProps) {
  if (evidencias.length === 0) {
    return (
      <span className="text-[0.9375rem] font-medium text-warning">
        [não verificado] — sem evidência coletada
      </span>
    );
  }

  return (
    <div className="flex flex-col gap-1.5">
      {evidencias.map((ev) => (
        <div key={ev.id} className="flex items-center gap-2">
          <span className="font-mono text-[0.8125rem] tabular-nums text-muted-foreground">
            {ev.id} · {shaCurto(ev.sha256)}
          </span>
          <a
            href={evidenciaArquivoUrl(casoId, ev.id)}
            download
            className={cn(
              "inline-flex shrink-0 items-center gap-1 rounded-sm border border-border bg-card px-2 py-1 text-[0.8125rem] text-primary",
              "transition-colors duration-[var(--dur-fast)] ease-[var(--ease-standard)]",
              "hover:border-primary hover:bg-primary-tint hover:shadow-[0_1px_2px_oklch(0.26_0.02_38_/_0.10)]",
              "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
            )}
          >
            <Download className="h-3.5 w-3.5" aria-hidden="true" />
            Baixar
          </a>
        </div>
      ))}
    </div>
  );
}
