"use client";

import * as React from "react";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { FormPesquisar } from "@/components/casos/form-pesquisar";
import { FormFolha } from "@/components/casos/form-folha";
import { FormInvestigar } from "@/components/casos/form-investigar";
import type { CasoDetalhe } from "@/lib/casos-types";
import { resumirHomonimos, type JobTipo } from "@/lib/job-resumo";

interface DossieAcoesProps {
  caso: CasoDetalhe;
  jobAtivo: { job_id: string; tipo: string } | null;
  onDisparado: (jobId: string, tipo: JobTipo) => void;
  /** Mensagem de `EvidenciaAmbigua` do último job de folha com erro — a UI
   *  pede a matrícula em vez de escolher sozinha (plano §4.2/§6.6). */
  folhaAmbigua: string | null;
}

const CONFIRMA_TEXTO: Record<string, string> = {
  folha: "Já há uma coleta de folha em andamento; aguarde ou acompanhe abaixo.",
  investigacao: "O assistente ainda está investigando; aguarde ou acompanhe abaixo.",
  pesquisa: "Já há uma pesquisa em andamento; aguarde ou acompanhe abaixo.",
};

type Acao = "pesquisar" | "folha" | "investigar" | null;

/** Seção 2 do dossiê (plano §1.2): três ações de trabalho longo. Job ativo
 *  no caso → confirmação antes de abrir outro formulário (plano §4.3, W0-F6),
 *  texto varia pelo `tipo` do job já em andamento. */
export function DossieAcoes({ caso, jobAtivo, onDisparado, folhaAmbigua }: DossieAcoesProps) {
  const [acaoAberta, setAcaoAberta] = React.useState<Acao>(null);
  const [focarMatricula, setFocarMatricula] = React.useState(false);

  function abrir(acao: Exclude<Acao, null>) {
    if (jobAtivo) {
      const texto = CONFIRMA_TEXTO[jobAtivo.tipo] ?? "Já há uma ação em andamento neste caso.";
      const prosseguir = window.confirm(`${texto}\n\nDisparar mesmo assim?`);
      if (!prosseguir) return;
    }
    setFocarMatricula(false);
    setAcaoAberta(acao);
  }

  function tentarFolhaComMatricula() {
    setFocarMatricula(true);
    setAcaoAberta("folha");
  }

  function fechar() {
    setAcaoAberta(null);
  }

  return (
    <section aria-labelledby="dossie-acoes-titulo">
      <h2 id="dossie-acoes-titulo" className="text-[1.0625rem] font-semibold leading-[1.35]">
        Ações
      </h2>

      {folhaAmbigua &&
        (() => {
          const homonimos = resumirHomonimos(folhaAmbigua);
          return (
            <div className="mt-3 flex items-start gap-3 rounded-md border border-warning bg-warning-tint p-4">
              <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-warning" aria-hidden="true" />
              <div>
                <p className="text-[0.9375rem] font-medium text-foreground">
                  Servidor ambíguo — o assistente não pode escolher sozinho
                </p>
                <p className="mt-1 text-[0.9375rem] text-foreground">{homonimos.prefixo}.</p>
                {homonimos.candidatosVisiveis.length > 0 && (
                  <ul className="mt-2 max-h-48 list-disc space-y-0.5 overflow-y-auto pl-5 text-[0.8125rem] text-muted-foreground">
                    {homonimos.candidatosVisiveis.map((candidato, i) => (
                      <li key={i}>{candidato}</li>
                    ))}
                  </ul>
                )}
                {homonimos.restantes > 0 && (
                  <details className="mt-2 text-[0.8125rem] text-muted-foreground">
                    <summary className="cursor-pointer">
                      … e mais {homonimos.restantes} homônimos — informe a matrícula para
                      desambiguar
                    </summary>
                    <p className="mt-1 whitespace-pre-wrap">{homonimos.textoCompleto}</p>
                  </details>
                )}
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  className="mt-2"
                  onClick={tentarFolhaComMatricula}
                >
                  Informar matrícula e tentar de novo
                </Button>
              </div>
            </div>
          );
        })()}

      <div className="mt-3 flex flex-wrap gap-3">
        <Button type="button" onClick={() => abrir("investigar")}>
          Investigar (assistente)
        </Button>
        <Button type="button" variant="secondary" onClick={() => abrir("pesquisar")}>
          Pesquisar registros
        </Button>
        <Button type="button" variant="secondary" onClick={() => abrir("folha")}>
          Coletar folha
        </Button>
      </div>

      <FormPesquisar
        open={acaoAberta === "pesquisar"}
        onClose={fechar}
        caso={caso}
        onDisparado={(jobId) => onDisparado(jobId, "pesquisa")}
      />
      <FormFolha
        open={acaoAberta === "folha"}
        onClose={fechar}
        caso={caso}
        focarMatricula={focarMatricula}
        onDisparado={(jobId) => onDisparado(jobId, "folha")}
      />
      <FormInvestigar
        open={acaoAberta === "investigar"}
        onClose={fechar}
        caso={caso}
        onDisparado={(jobId) => onDisparado(jobId, "investigacao")}
      />
    </section>
  );
}
