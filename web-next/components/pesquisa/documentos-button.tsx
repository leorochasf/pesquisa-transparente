"use client";

import { useEffect, useRef, useState } from "react";
import { Download, FileText, Loader2 } from "lucide-react";
import { api, ApiError, anexoDownloadUrl } from "@/lib/api";
import type { AnexoOut, RefRegistro } from "@/lib/api-types";
import { cn } from "@/lib/utils";

type SecaoAnexo = "contratos" | "licitacoes" | "dispensas";

interface Props {
  slug: string;
  secao: SecaoAnexo;
  refRegistro?: RefRegistro;
}

const TRANSITION = "transition-colors duration-[var(--dur-fast)] ease-[var(--ease-standard)]";

/** Botão "Documentos": abre um painel com os anexos do registro (busca lazy,
 *  só ao clicar) e um link "Baixar" por anexo, apontando para o proxy de
 *  download (o navegador baixa o PDF direto, sem passar por fetch/blob).
 *  Estilo conforme DESIGN.md — componente button-download-pdf. */
export function DocumentosButton({ slug, secao, refRegistro }: Props) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [anexos, setAnexos] = useState<AnexoOut[] | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const escHandler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    document.addEventListener("keydown", escHandler);
    return () => {
      document.removeEventListener("mousedown", handler);
      document.removeEventListener("keydown", escHandler);
    };
  }, [open]);

  if (!refRegistro?.id) return null;

  async function toggle() {
    const next = !open;
    setOpen(next);
    if (next && anexos === null && !loading) {
      setLoading(true);
      setError(null);
      try {
        const data = await api.listarAnexos(slug, secao, refRegistro!);
        setAnexos(data);
      } catch (e) {
        setError(
          e instanceof ApiError
            ? e.message
            : "Não foi possível carregar os documentos deste registro.",
        );
      } finally {
        setLoading(false);
      }
    }
  }

  return (
    <div ref={containerRef} className="relative inline-block">
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        aria-busy={loading || undefined}
        disabled={loading}
        className={cn(
          "inline-flex items-center gap-1.5 rounded-sm border border-border bg-card px-2.5 py-1.5 text-[0.9375rem] text-primary",
          TRANSITION,
          "hover:border-primary hover:bg-primary-tint hover:shadow-[0_1px_2px_oklch(0.26_0.02_38_/_0.10)]",
          "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
          "disabled:cursor-not-allowed disabled:opacity-70",
        )}
      >
        {loading ? (
          <Loader2 className="h-4 w-4 shrink-0 animate-spin" aria-hidden="true" />
        ) : (
          <FileText className="h-4 w-4 shrink-0" aria-hidden="true" />
        )}
        Documentos
      </button>
      {open && (
        <div
          role="region"
          aria-label="Documentos do registro"
          className="absolute right-0 z-[var(--z-dropdown)] mt-2 w-72 rounded-md border border-border bg-card p-3 text-[0.9375rem] text-card-foreground shadow-[0_8px_24px_-8px_oklch(0.26_0.02_38_/_0.18)]"
        >
          {loading && (
            <p className="flex items-center gap-2 text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              Carregando documentos, isso pode levar alguns segundos…
            </p>
          )}
          {!loading && error && <p className="text-destructive">{error}</p>}
          {!loading && !error && anexos && anexos.length === 0 && (
            <p className="text-muted-foreground">Nenhum documento disponível neste registro.</p>
          )}
          {!loading && !error && anexos && anexos.length > 0 && (
            <ul className="space-y-1">
              {anexos.map((a, i) => (
                <li key={`${a.ref}-${i}`} className="flex items-center justify-between gap-3">
                  <span className="truncate">{a.rotulo}</span>
                  <a
                    href={anexoDownloadUrl(slug, secao, a.ref)}
                    className={cn(
                      "inline-flex shrink-0 items-center gap-1 rounded-sm border border-border bg-card px-2 py-1 text-primary",
                      TRANSITION,
                      "hover:border-primary hover:bg-primary-tint",
                      "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
                    )}
                  >
                    <Download className="h-3.5 w-3.5" aria-hidden="true" />
                    Baixar
                  </a>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
