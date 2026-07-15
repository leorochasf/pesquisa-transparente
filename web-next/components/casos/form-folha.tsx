"use client";

import * as React from "react";
import { Plus, X } from "lucide-react";
import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { ErrorState } from "@/components/shared/error-state";
import { casosApi } from "@/lib/casos-api";
import { ApiError } from "@/lib/api";
import { MUNICIPIOS_CASO } from "@/components/casos/caso-tipo";
import type { CasoDetalhe, Competencia } from "@/lib/casos-types";

interface FormFolhaProps {
  open: boolean;
  onClose: () => void;
  caso: CasoDetalhe;
  onDisparado: (jobId: string) => void;
  /** Reabertura após `EvidenciaAmbigua` (plano §4.2/§6.6) — foca a matrícula
   *  em vez de deixar o jurista escolher sozinho entre homônimos. */
  focarMatricula?: boolean;
}

const MUNICIPIO_OPTIONS = MUNICIPIOS_CASO.map((m) => ({ value: m.value, label: m.label }));

function novaCompetencia(): Competencia {
  const hoje = new Date();
  return { ano: hoje.getFullYear(), mes: hoje.getMonth() + 1 };
}

/** Formulário de `POST /folha` — servidor + competências múltiplas não
 *  contíguas (plano §1.2 seção 2). */
export function FormFolha({ open, onClose, caso, onDisparado, focarMatricula }: FormFolhaProps) {
  const [municipio, setMunicipio] = React.useState(caso.municipios[0] ?? "");
  const [servidor, setServidor] = React.useState(caso.alvos.servidor ?? "");
  const [matricula, setMatricula] = React.useState("");
  const [competencias, setCompetencias] = React.useState<Competencia[]>([novaCompetencia()]);
  const [loading, setLoading] = React.useState(false);
  const [erro, setErro] = React.useState<string | null>(null);
  const matriculaRef = React.useRef<HTMLInputElement | null>(null);

  React.useEffect(() => {
    if (open && focarMatricula) {
      matriculaRef.current?.focus();
    }
  }, [open, focarMatricula]);

  function resetForm() {
    setMunicipio(caso.municipios[0] ?? "");
    setServidor(caso.alvos.servidor ?? "");
    setMatricula("");
    setCompetencias([novaCompetencia()]);
    setErro(null);
  }

  function handleClose() {
    if (loading) return;
    resetForm();
    onClose();
  }

  function addCompetencia() {
    setCompetencias((prev) => [...prev, novaCompetencia()]);
  }

  function removeCompetencia(i: number) {
    setCompetencias((prev) => prev.filter((_, idx) => idx !== i));
  }

  function updateCompetencia(i: number, campo: "ano" | "mes", valor: number) {
    setCompetencias((prev) => prev.map((c, idx) => (idx === i ? { ...c, [campo]: valor } : c)));
  }

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setErro(null);

    if (!municipio) {
      setErro("Selecione o município.");
      return;
    }
    if (!servidor.trim()) {
      setErro("Informe o servidor (nome ou matrícula).");
      return;
    }
    if (competencias.length === 0) {
      setErro("Adicione ao menos uma competência.");
      return;
    }
    for (const c of competencias) {
      if (c.mes < 1 || c.mes > 12) {
        setErro("Mês deve estar entre 1 e 12.");
        return;
      }
    }

    setLoading(true);
    try {
      const { job_id } = await casosApi.folhaCaso(caso.id, {
        municipio,
        servidor: servidor.trim(),
        matricula: matricula.trim() || undefined,
        competencias,
      });
      resetForm();
      onClose();
      onDisparado(job_id);
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Não foi possível disparar a coleta de folha.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Dialog open={open} onClose={handleClose} title="Coletar folha">
      <form onSubmit={onSubmit} className="space-y-4" aria-busy={loading || undefined}>
        {erro && <ErrorState message={erro} />}

        <div>
          <label htmlFor="folha-municipio" className="mb-1 block text-[0.9375rem] font-medium">
            Município
          </label>
          <Select
            id="folha-municipio"
            value={municipio}
            onChange={(e) => setMunicipio(e.target.value)}
            options={MUNICIPIO_OPTIONS}
            required
            disabled={loading}
          />
        </div>

        <div>
          <label htmlFor="folha-servidor" className="mb-1 block text-[0.9375rem] font-medium">
            Servidor (nome ou matrícula)
          </label>
          <Input
            id="folha-servidor"
            value={servidor}
            onChange={(e) => setServidor(e.target.value)}
            placeholder="Nome completo ou matrícula"
            disabled={loading}
          />
        </div>

        <div>
          <label htmlFor="folha-matricula" className="mb-1 block text-[0.9375rem] font-medium">
            Matrícula (desambigua homônimos)
          </label>
          <Input
            id="folha-matricula"
            ref={matriculaRef}
            value={matricula}
            onChange={(e) => setMatricula(e.target.value)}
            placeholder="Opcional, a menos que o serviço peça"
            disabled={loading}
          />
        </div>

        <fieldset disabled={loading}>
          <legend className="mb-1 block text-[0.9375rem] font-medium">
            Competências (mês/ano — podem ser não contíguas)
          </legend>
          <div className="space-y-2">
            {competencias.map((c, i) => (
              <div key={i} className="flex items-center gap-2">
                <Input
                  aria-label={`Mês da competência ${i + 1}`}
                  inputMode="numeric"
                  value={String(c.mes)}
                  onChange={(e) =>
                    updateCompetencia(i, "mes", Number(e.target.value.replace(/\D/g, "") || 0))
                  }
                  className="w-20"
                  placeholder="MM"
                />
                <span className="text-muted-foreground">/</span>
                <Input
                  aria-label={`Ano da competência ${i + 1}`}
                  inputMode="numeric"
                  value={String(c.ano)}
                  onChange={(e) =>
                    updateCompetencia(i, "ano", Number(e.target.value.replace(/\D/g, "") || 0))
                  }
                  className="w-24"
                  placeholder="AAAA"
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  onClick={() => removeCompetencia(i)}
                  disabled={competencias.length === 1}
                  aria-label={`Remover competência ${i + 1}`}
                >
                  <X className="h-4 w-4" aria-hidden="true" />
                </Button>
              </div>
            ))}
          </div>
          <Button type="button" variant="secondary" size="sm" onClick={addCompetencia} className="mt-2">
            <Plus className="h-3.5 w-3.5" aria-hidden="true" />
            Adicionar competência
          </Button>
        </fieldset>

        <div className="flex justify-end gap-3 pt-2">
          <Button type="button" variant="secondary" onClick={handleClose} disabled={loading}>
            Cancelar
          </Button>
          <Button type="submit" loading={loading}>
            {loading ? "Disparando…" : "Coletar folha"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
