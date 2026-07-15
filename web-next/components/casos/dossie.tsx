"use client";

import * as React from "react";
import type { Route } from "next";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { AlertCircle } from "lucide-react";
import { useCaso } from "@/hooks/use-casos";
import { gravarJobAtivo, lerJobAtivo } from "@/hooks/use-job";
import { jobTipo, type JobTipo } from "@/lib/job-resumo";
import { DossieCabecalho } from "@/components/casos/dossie-cabecalho";
import { DossieAcoes } from "@/components/casos/dossie-acoes";
import { JobProgresso } from "@/components/casos/job-progresso";
import { DossieItens } from "@/components/casos/dossie-itens";
import { DossieLacunas } from "@/components/casos/dossie-lacunas";
import { DossieRelatorio } from "@/components/casos/dossie-relatorio";
import { ErrorState } from "@/components/shared/error-state";
import { Skeleton, TableSkeleton } from "@/components/shared/skeleton";
import type { Job, ResultadoFolha } from "@/lib/casos-types";

interface JobAtivo {
  job_id: string;
  tipo: string;
}

/** Distingue `EvidenciaAmbigua` (erro+competência, sem avisos — api.py:586-593)
 *  do erro geral de folha (só `erro` — api.py:611). Plano §4.2/§6.6: nesse
 *  caso a UI pede a matrícula, nunca escolhe sozinha entre homônimos. */
function evidenciaAmbiguaDe(job: Job): string | null {
  if (jobTipo(job) !== "folha" || job.status !== "erro") return null;
  const r = job.resultado_resumo as ResultadoFolha | null;
  return r?.erro && r?.competencia ? r.erro : null;
}

/** Orquestrador do dossiê (plano §1.2): compõe as 6 seções empilhadas num
 *  scroll único. Dono da sobrevivência a refresh (§4.3) — reidrata o job
 *  ativo lendo primeiro `?job=` da URL, depois o localStorage por caso+ação,
 *  e mantém os dois em sincronia via `router.replace` sem recarregar. */
export function Dossie({ casoId }: { casoId: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { data: caso, error, loading, refetch } = useCaso(casoId);

  // `jobExibido` fica montado mesmo após o job terminar — é o que faz o
  // painel de acompanhamento "virar um resumo" (plano §4.1) em vez de
  // desaparecer no instante em que o status vira terminal. `jobRodando`
  // é o que efetivamente bloqueia nova ação (W0-F6): true só enquanto o job
  // exibido está `fila`/`rodando`.
  const [jobExibido, setJobExibido] = React.useState<JobAtivo | null>(null);
  const [jobRodando, setJobRodando] = React.useState(false);
  const [ultimoJob, setUltimoJob] = React.useState<Job | null>(null);
  const [folhaAmbigua, setFolhaAmbigua] = React.useState<string | null>(null);
  const [atualizarEm, setAtualizarEm] = React.useState(0);
  const reidratado = React.useRef(false);

  function atualizarQueryJob(jobId: string | null) {
    const qs = new URLSearchParams(searchParams.toString());
    if (jobId) qs.set("job", jobId);
    else qs.delete("job");
    const query = qs.toString();
    router.replace((query ? `${pathname}?${query}` : pathname) as Route, { scroll: false });
  }

  React.useEffect(() => {
    if (reidratado.current) return;
    reidratado.current = true;
    const jobDaQuery = searchParams.get("job");
    const salvo = lerJobAtivo(casoId);
    if (jobDaQuery) {
      const tipo = salvo && salvo.job_id === jobDaQuery ? salvo.tipo : "";
      setJobExibido({ job_id: jobDaQuery, tipo });
      setJobRodando(true);
    } else if (salvo) {
      setJobExibido(salvo);
      setJobRodando(true);
      atualizarQueryJob(salvo.job_id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [casoId]);

  function aoDisparar(jobId: string, tipo: JobTipo) {
    gravarJobAtivo(casoId, jobId, tipo);
    setJobExibido({ job_id: jobId, tipo });
    setJobRodando(true);
    setFolhaAmbigua(null);
    atualizarQueryJob(jobId);
  }

  function aoConcluirJob(job: Job) {
    setUltimoJob(job);
    setJobRodando(false);
    atualizarQueryJob(null);
    setAtualizarEm((v) => v + 1);
    void refetch();
    setFolhaAmbigua(evidenciaAmbiguaDe(job));
  }

  function aoNaoEncontrarJob() {
    setJobExibido(null);
    setJobRodando(false);
    atualizarQueryJob(null);
  }

  function aoConhecerTipoJob(tipo: JobTipo) {
    setJobExibido((prev) => (prev && prev.tipo !== tipo ? { ...prev, tipo } : prev));
  }

  // `loading` também fica `true` durante um refetch em segundo plano (ex.:
  // ao concluir um job) — o skeleton de página inteira é só para a carga
  // inicial (`!caso`); um refetch com dado já em mãos não deve apagar o
  // dossiê inteiro (apagaria o próprio resumo do job que acabou de terminar).
  if (loading && !caso) {
    return (
      <div className="space-y-8">
        <div className="space-y-3 border-b border-border pb-6">
          <Skeleton className="h-7 w-2/3" />
          <Skeleton className="h-4 w-1/3" />
        </div>
        <TableSkeleton rows={4} cols={4} />
      </div>
    );
  }

  if (error && !caso && error.status === 404) {
    return (
      <div role="alert" className="rounded-md border border-destructive bg-destructive-tint p-4">
        <div className="flex gap-3">
          <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-destructive" aria-hidden="true" />
          <div>
            <p className="text-[1.0625rem] font-semibold leading-[1.35]">Caso não encontrado</p>
            <Link
              href="/casos"
              className="mt-3 inline-block text-[0.9375rem] text-primary underline underline-offset-2 hover:text-primary-hover"
            >
              Ver todos os casos
            </Link>
          </div>
        </div>
      </div>
    );
  }

  if (!caso) {
    return (
      <ErrorState
        title="Falha ao carregar o caso"
        message={error?.message ?? "Erro desconhecido."}
        onRetry={refetch}
      />
    );
  }

  return (
    <div className="space-y-8">
      <DossieCabecalho caso={caso} />

      <DossieAcoes
        caso={caso}
        jobAtivo={jobRodando ? jobExibido : null}
        onDisparado={aoDisparar}
        folhaAmbigua={folhaAmbigua}
      />

      {jobExibido && (
        <section aria-labelledby="dossie-acompanhamento-titulo">
          <h2
            id="dossie-acompanhamento-titulo"
            className="text-[1.0625rem] font-semibold leading-[1.35]"
          >
            Acompanhamento
          </h2>
          <div className="mt-3">
            <JobProgresso
              key={jobExibido.job_id}
              jobId={jobExibido.job_id}
              casoId={casoId}
              onDone={aoConcluirJob}
              onNaoEncontrado={aoNaoEncontrarJob}
              onTipoConhecido={aoConhecerTipoJob}
            />
          </div>
        </section>
      )}

      <DossieItens caso={caso} />
      <DossieLacunas caso={caso} ultimoJob={ultimoJob} />
      <DossieRelatorio caso={caso} atualizarEm={atualizarEm} />
    </div>
  );
}
