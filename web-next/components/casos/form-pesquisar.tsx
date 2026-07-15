"use client";

import * as React from "react";
import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ErrorState } from "@/components/shared/error-state";
import { casosApi } from "@/lib/casos-api";
import { ApiError } from "@/lib/api";
import { MUNICIPIOS_CASO } from "@/components/casos/caso-tipo";
import type { CasoDetalhe } from "@/lib/casos-types";

interface FormPesquisarProps {
  open: boolean;
  onClose: () => void;
  caso: CasoDetalhe;
  onDisparado: (jobId: string) => void;
}

/** Formulário de `POST /pesquisar` — varredura manual (plano §1.2 seção 2). */
export function FormPesquisar({ open, onClose, caso, onDisparado }: FormPesquisarProps) {
  const [q, setQ] = React.useState("");
  const [municipios, setMunicipios] = React.useState<string[]>([]);
  const [ano, setAno] = React.useState("");
  const [mes, setMes] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [erro, setErro] = React.useState<string | null>(null);

  function resetForm() {
    setQ("");
    setMunicipios([]);
    setAno("");
    setMes("");
    setErro(null);
  }

  function handleClose() {
    if (loading) return;
    resetForm();
    onClose();
  }

  function toggleMunicipio(slug: string) {
    setMunicipios((prev) => (prev.includes(slug) ? prev.filter((m) => m !== slug) : [...prev, slug]));
  }

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setErro(null);
    setLoading(true);
    try {
      const { job_id } = await casosApi.pesquisarCaso(caso.id, {
        q: q.trim() || undefined,
        municipios: municipios.length > 0 ? municipios : undefined,
        ano: ano ? Number(ano) : undefined,
        mes: mes ? Number(mes) : undefined,
      });
      resetForm();
      onClose();
      onDisparado(job_id);
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Não foi possível disparar a pesquisa.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Dialog open={open} onClose={handleClose} title="Pesquisar registros">
      <form onSubmit={onSubmit} className="space-y-4" aria-busy={loading || undefined}>
        {erro && <ErrorState message={erro} />}
        <p className="text-[0.9375rem] text-muted-foreground">
          Varre os portais dos municípios selecionados. Deixe em branco para usar os alvos do
          caso e todos os municípios já cadastrados.
        </p>

        <div>
          <label htmlFor="pesq-q" className="mb-1 block text-[0.9375rem] font-medium">
            Termo de busca (opcional)
          </label>
          <Input
            id="pesq-q"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Ex.: nome do alvo ou CNPJ"
            disabled={loading}
          />
        </div>

        <fieldset disabled={loading}>
          <legend className="mb-1 block text-[0.9375rem] font-medium">
            Municípios a varrer (opcional)
          </legend>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {MUNICIPIOS_CASO.filter((m) => caso.municipios.includes(m.value)).map((m) => (
              <label
                key={m.value}
                className="flex items-center gap-2 rounded-sm border border-input px-2 py-1.5 text-[0.875rem] text-foreground"
              >
                <input
                  type="checkbox"
                  checked={municipios.includes(m.value)}
                  onChange={() => toggleMunicipio(m.value)}
                  className="h-4 w-4 rounded-sm border-input text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                />
                {m.label}
              </label>
            ))}
          </div>
        </fieldset>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label htmlFor="pesq-ano" className="mb-1 block text-[0.9375rem] font-medium">
              Ano (opcional)
            </label>
            <Input
              id="pesq-ano"
              inputMode="numeric"
              value={ano}
              onChange={(e) => setAno(e.target.value.replace(/\D/g, ""))}
              placeholder="2025"
              disabled={loading}
            />
          </div>
          <div>
            <label htmlFor="pesq-mes" className="mb-1 block text-[0.9375rem] font-medium">
              Mês (opcional)
            </label>
            <Input
              id="pesq-mes"
              inputMode="numeric"
              value={mes}
              onChange={(e) => setMes(e.target.value.replace(/\D/g, ""))}
              placeholder="1–12"
              disabled={loading}
            />
          </div>
        </div>

        <div className="flex justify-end gap-3 pt-2">
          <Button type="button" variant="secondary" onClick={handleClose} disabled={loading}>
            Cancelar
          </Button>
          <Button type="submit" loading={loading}>
            {loading ? "Disparando…" : "Pesquisar"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
