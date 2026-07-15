"use client";

import * as React from "react";
import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/shared/error-state";
import { casosApi } from "@/lib/casos-api";
import { ApiError } from "@/lib/api";
import type { CasoDetalhe } from "@/lib/casos-types";

interface FormInvestigarProps {
  open: boolean;
  onClose: () => void;
  caso: CasoDetalhe;
  onDisparado: (jobId: string) => void;
}

const MENSAGEM_INDISPONIVEL = "Assistente indisponível: chave do assistente não configurada.";

/** Formulário de `POST /investigar` — assistente autônomo (plano §1.2 seção
 *  2). Sem `OPENROUTER_API_KEY` o backend responde 400; a UI trata como
 *  "assistente indisponível" sem quebrar (plano §7). */
export function FormInvestigar({ open, onClose, caso, onDisparado }: FormInvestigarProps) {
  const [descricao, setDescricao] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [erro, setErro] = React.useState<string | null>(null);

  function resetForm() {
    setDescricao("");
    setErro(null);
  }

  function handleClose() {
    if (loading) return;
    resetForm();
    onClose();
  }

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setErro(null);
    setLoading(true);
    try {
      const { job_id } = await casosApi.investigarCaso(caso.id, {
        descricao: descricao.trim() || undefined,
      });
      resetForm();
      onClose();
      onDisparado(job_id);
    } catch (e) {
      if (e instanceof ApiError && e.status === 400) {
        setErro(MENSAGEM_INDISPONIVEL);
      } else {
        setErro(e instanceof ApiError ? e.message : "Não foi possível disparar a investigação.");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <Dialog open={open} onClose={handleClose} title="Investigar (assistente)">
      <form onSubmit={onSubmit} className="space-y-4" aria-busy={loading || undefined}>
        {erro && <ErrorState message={erro} />}
        <p className="text-[0.9375rem] text-muted-foreground">
          O assistente planeja e executa etapas de investigação sozinho, com custo real de
          tokens (o valor gasto aparece no acompanhamento ao concluir).
        </p>

        <div>
          <label htmlFor="inv-descricao" className="mb-1 block text-[0.9375rem] font-medium">
            Descrição da investigação (opcional)
          </label>
          <textarea
            id="inv-descricao"
            value={descricao}
            onChange={(e) => setDescricao(e.target.value)}
            placeholder="Deixe em branco para o assistente derivar do caso (título, tipo e alvos)."
            disabled={loading}
            rows={4}
            className="block w-full rounded-sm border border-input bg-background px-3 py-2 text-[0.9375rem] text-foreground transition-colors duration-[var(--dur-fast)] ease-[var(--ease-standard)] placeholder:text-muted-foreground hover:border-foreground focus-visible:border-ring focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:border-border disabled:bg-muted disabled:text-muted-foreground"
          />
        </div>

        <div className="flex justify-end gap-3 pt-2">
          <Button type="button" variant="secondary" onClick={handleClose} disabled={loading}>
            Cancelar
          </Button>
          <Button type="submit" loading={loading}>
            {loading ? "Disparando…" : "Investigar"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
