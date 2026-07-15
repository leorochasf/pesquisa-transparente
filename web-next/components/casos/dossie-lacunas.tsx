import { AlertTriangle } from "lucide-react";
import { EmptyState } from "@/components/shared/empty-state";
import { jobTipo } from "@/lib/job-resumo";
import type { CasoDetalhe, Job, ResultadoFolha, ResultadoInvestigacao, ResultadoPesquisa } from "@/lib/casos-types";

/** Ressalvas do último job concluído no ar (plano §1.2 seção 5): avisos de
 *  varredura truncada (pesquisa), competências que falharam (folha), lacunas
 *  e teto atingido (investigação). Defensivo (W0-F2) — cada campo é opcional
 *  e checado por presença antes do uso. */
function ressalvasDoUltimoJob(job: Job | null): string[] {
  if (!job || !job.resultado_resumo) return [];
  const tipo = jobTipo(job);
  if (tipo === "pesquisa") {
    const r = job.resultado_resumo as ResultadoPesquisa;
    return r.avisos ?? [];
  }
  if (tipo === "folha") {
    const r = job.resultado_resumo as ResultadoFolha;
    return (r.falhas ?? []).map((f) => `Competência ${f.competencia}: ${f.erro}`);
  }
  const r = job.resultado_resumo as ResultadoInvestigacao;
  const ressalvas = [...(r.lacunas ?? [])];
  if (r.teto_atingido) {
    ressalvas.push("Entrega parcial: o teto de custo/tempo foi atingido.");
  }
  return ressalvas;
}

/** Seção 5 do dossiê (plano §1.2/§6.2): lacunas e ressalvas em destaque —
 *  bloco `warning-tint` com borda completa (nunca side-stripe), posicionado
 *  antes do relatório. Duas fontes: (1) itens do caso sem nenhuma evidência
 *  vinculada, ao vivo; (2) avisos/falhas/lacunas do último job concluído
 *  nesta sessão (pesquisa/folha/investigação). */
export function DossieLacunas({ caso, ultimoJob }: { caso: CasoDetalhe; ultimoJob?: Job | null }) {
  const itensSemEvidencia = caso.itens.filter(
    (item) => !caso.evidencias.some((e) => e.item_id === item.id),
  );
  const ressalvasJob = ressalvasDoUltimoJob(ultimoJob ?? null);

  return (
    <section aria-labelledby="dossie-lacunas-titulo">
      <h2 id="dossie-lacunas-titulo" className="text-[1.0625rem] font-semibold leading-[1.35]">
        Lacunas e ressalvas
      </h2>
      {caso.itens.length === 0 && ressalvasJob.length === 0 ? (
        <div className="mt-3">
          <EmptyState
            title="Nenhum registro ainda"
            description="Use “Investigar” para o assistente varrer, ou “Pesquisar registros” / “Coletar folha” para buscar você mesmo."
          />
        </div>
      ) : (
        <div className="mt-3 rounded-md border border-warning bg-warning-tint p-4">
          {itensSemEvidencia.length === 0 && ressalvasJob.length === 0 ? (
            <p className="text-[0.9375rem] text-foreground">
              Nenhuma lacuna identificada — todo item deste caso tem ao menos uma evidência
              coletada.
            </p>
          ) : (
            <div className="flex gap-3">
              <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-warning" aria-hidden="true" />
              <div className="space-y-3">
                {itensSemEvidencia.length > 0 && (
                  <div>
                    <p className="text-[0.9375rem] font-medium text-foreground">
                      {itensSemEvidencia.length} item(ns) sem evidência coletada
                    </p>
                    <ul className="mt-2 list-disc space-y-1 pl-5 text-[0.9375rem] text-foreground">
                      {itensSemEvidencia.map((item) => (
                        <li key={item.id}>
                          {item.titulo ?? item.documento ?? item.id} —{" "}
                          <span className="font-medium text-warning">[não verificado]</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {ressalvasJob.length > 0 && (
                  <div>
                    <p className="text-[0.9375rem] font-medium text-foreground">
                      Ressalvas da última ação executada
                    </p>
                    <ul className="mt-2 list-disc space-y-1 pl-5 text-[0.9375rem] text-foreground">
                      {ressalvasJob.map((texto, i) => (
                        <li key={i}>{texto}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
