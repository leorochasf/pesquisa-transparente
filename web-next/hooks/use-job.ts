"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api";
import { casosApi } from "@/lib/casos-api";
import type { Job } from "@/lib/casos-types";

const POLL_INTERVAL_MS = 2_500;
const STATUS_TERMINAIS: Job["status"][] = ["concluida", "erro", "interrompida"];

function jobAtivoKey(casoId: string): string {
  return `bt:caso:${casoId}:jobAtivo`;
}

/** Lê/grava/limpa o slot de job ativo de um caso (plano §4.3 — só um job
 *  ativo por caso na UI; as três ações compartilham este slot). Usado pelo
 *  disparo da ação (W3, `dossie-acoes.tsx`) e limpo aqui em `useJob` quando o
 *  job termina ou não existe mais (W0-F5). */
export function lerJobAtivo(casoId: string): { job_id: string; tipo: string } | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(jobAtivoKey(casoId));
  if (!raw) return null;
  try {
    return JSON.parse(raw) as { job_id: string; tipo: string };
  } catch {
    return null;
  }
}

export function gravarJobAtivo(casoId: string, jobId: string, tipo: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(jobAtivoKey(casoId), JSON.stringify({ job_id: jobId, tipo }));
}

export function limparJobAtivo(casoId: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(jobAtivoKey(casoId));
}

/** Mapa status→texto pt-BR (plano §4.2). Nunca "status"/"job" cru na UI. */
const STATUS_TEXTO: Record<Job["status"], string> = {
  fila: "Na fila…",
  rodando: "Em andamento…",
  concluida: "Concluída",
  erro: "Falhou",
  interrompida: "Interrompida (o serviço reiniciou) — refaça a ação",
};

export function statusTexto(status: Job["status"]): string {
  return STATUS_TEXTO[status];
}

/** Variante de badge (plano §4.2, coluna "Cor"). */
export type StatusBadgeVariant = "secondary" | "info" | "success" | "warning" | "destructive";

const STATUS_BADGE_VARIANT: Record<Job["status"], StatusBadgeVariant> = {
  fila: "secondary",
  rodando: "info",
  concluida: "success",
  erro: "destructive",
  interrompida: "warning",
};

export function statusBadgeVariant(status: Job["status"]): StatusBadgeVariant {
  return STATUS_BADGE_VARIANT[status];
}

/** Hook de acompanhamento de trabalho longo (plano §4). Faz
 *  `GET /api/jobs/{jobId}` a cada 2,5s e para quando o status é terminal
 *  (`concluida`/`erro`/`interrompida`), disparando `onDone`.
 *
 *  W0-F5 — se `casoId` for informado e o job responder 404 (base recriada,
 *  ou `jobId` de outra base), limpa o slot `bt:caso:<casoId>:jobAtivo`
 *  silenciosamente e para de tentar — nenhum erro ruidoso, nenhum retry-loop. */
export function useJob(
  jobId: string | null,
  options?: { casoId?: string; onDone?: (job: Job) => void },
) {
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [notFound, setNotFound] = useState(false);
  const onDoneRef = useRef(options?.onDone);
  onDoneRef.current = options?.onDone;
  const casoId = options?.casoId;

  useEffect(() => {
    if (!jobId) {
      setJob(null);
      setError(null);
      setNotFound(false);
      return;
    }
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | null = null;

    async function poll() {
      try {
        const data = await casosApi.obterJob(jobId as string);
        if (!alive) return;
        setJob(data);
        setError(null);
        if (STATUS_TERMINAIS.includes(data.status)) {
          if (casoId) limparJobAtivo(casoId);
          onDoneRef.current?.(data);
          return;
        }
        timer = setTimeout(poll, POLL_INTERVAL_MS);
      } catch (e) {
        if (!alive) return;
        const apiErr = e instanceof ApiError ? e : new ApiError(String(e), 0, null);
        if (apiErr.status === 404) {
          if (casoId) limparJobAtivo(casoId);
          setJob(null);
          setError(null);
          setNotFound(true);
          return;
        }
        setError(apiErr);
        timer = setTimeout(poll, POLL_INTERVAL_MS);
      }
    }

    void poll();
    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
    };
  }, [jobId, casoId]);

  return { job, error, notFound };
}
