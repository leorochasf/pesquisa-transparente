"use client";

import * as React from "react";
import { Badge } from "@/components/ui/badge";
import { statusBadgeVariant, statusTexto, useJob } from "@/hooks/use-job";
import { jobTipo, progressoTexto, resumoTexto, type JobTipo } from "@/lib/job-resumo";
import type { Job, ProgressoFolha, ProgressoPesquisa } from "@/lib/casos-types";

interface JobProgressoProps {
  jobId: string;
  casoId: string;
  onDone: (job: Job) => void;
  /** 404 na reidratação (W0-F5): job some do banco (base recriada) — a UI
   *  já limpa o slot de localStorage sozinha (`useJob`); este callback avisa
   *  o orquestrador do dossiê para também limpar o espelho `?job=` da URL. */
  onNaoEncontrado?: () => void;
  /** Dispara uma vez, assim que o `tipo` real do job é conhecido (o slot
   *  gravado por engano/reidratado por query pode não ter o tipo certo) —
   *  usado para a confirmação por `tipo` do W0-F6. */
  onTipoConhecido?: (tipo: JobTipo) => void;
}

/** Painel de acompanhamento (plano §1.2 seção 3, §4.2, §5). Sem barra
 *  decorativa gratuita: barra fina só quando há `feitos/total` determinístico
 *  (pesquisa/folha); investigação usa texto de etapa + badge, sem spinner
 *  infinito. `aria-live="polite"` anuncia o avanço sem roubar foco. */
export function JobProgresso({ jobId, casoId, onDone, onNaoEncontrado, onTipoConhecido }: JobProgressoProps) {
  const { job, error, notFound } = useJob(jobId, { casoId, onDone });

  React.useEffect(() => {
    if (notFound) onNaoEncontrado?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [notFound]);

  React.useEffect(() => {
    if (job) onTipoConhecido?.(jobTipo(job));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.id]);

  if (!job) {
    return error ? (
      <p className="text-[0.9375rem] text-muted-foreground">
        Não foi possível consultar o andamento agora — tentando de novo…
      </p>
    ) : null;
  }

  const tipo = jobTipo(job);
  const progresso = progressoTexto(job);
  const resumo = resumoTexto(job);
  const barra = barraDeterministica(job, tipo);

  return (
    <div aria-live="polite" className="rounded-md border border-border bg-card p-4">
      <div className="flex items-center gap-2">
        <Badge variant={statusBadgeVariant(job.status)} dot>
          {statusTexto(job.status)}
        </Badge>
        <span className="text-[0.6875rem] uppercase tracking-[0.06em] text-muted-foreground">
          {tipo === "pesquisa" ? "Pesquisa" : tipo === "folha" ? "Folha" : "Investigação"}
        </span>
      </div>

      {progresso && !resumo && (
        <p className="mt-2 text-[0.9375rem] text-foreground">{progresso}</p>
      )}

      {barra && (
        <div
          className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-muted"
          role="progressbar"
          aria-label={
            tipo === "pesquisa"
              ? "Progresso da pesquisa"
              : tipo === "folha"
                ? "Progresso da coleta de folha"
                : "Progresso da investigação"
          }
          aria-valuenow={barra.feitos}
          aria-valuemin={0}
          aria-valuemax={barra.total}
        >
          <div
            className="h-full rounded-full bg-primary transition-[width] duration-[var(--dur-base)] ease-[var(--ease-standard)]"
            style={{ width: `${barra.total > 0 ? (barra.feitos / barra.total) * 100 : 0}%` }}
          />
        </div>
      )}

      {resumo && (
        <div className="mt-3">
          <p
            className={
              resumo.tom === "destructive"
                ? "text-[0.9375rem] font-medium text-destructive"
                : resumo.tom === "warning"
                  ? "text-[0.9375rem] font-medium text-warning"
                  : "text-[0.9375rem] font-medium text-foreground"
            }
          >
            {resumo.texto}
          </p>
          {resumo.extras && resumo.extras.length > 0 && (
            <ul className="mt-1.5 list-disc space-y-0.5 pl-5 text-[0.875rem] text-muted-foreground">
              {resumo.extras.map((extra, i) => (
                <li key={i}>{extra}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function barraDeterministica(
  job: Job,
  tipo: "pesquisa" | "folha" | "investigacao",
): { feitos: number; total: number } | null {
  if (!job.progresso || (job.status !== "fila" && job.status !== "rodando")) return null;
  if (tipo === "pesquisa") {
    const p = job.progresso as ProgressoPesquisa;
    return { feitos: p.municipios_feitos, total: p.municipios_total };
  }
  if (tipo === "folha") {
    const p = job.progresso as ProgressoFolha;
    return { feitos: p.feitas, total: p.total };
  }
  return null;
}
