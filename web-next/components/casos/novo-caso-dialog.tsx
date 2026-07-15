"use client";

import * as React from "react";
import type { Route } from "next";
import { useRouter } from "next/navigation";
import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { ErrorState } from "@/components/shared/error-state";
import { casosApi } from "@/lib/casos-api";
import { ApiError } from "@/lib/api";
import { MUNICIPIOS_CASO, TIPOS_CASO, type TipoCaso } from "@/components/casos/caso-tipo";
import type { CasoAlvos } from "@/lib/casos-types";

interface NovoCasoDialogProps {
  open: boolean;
  onClose: () => void;
}

const TIPO_OPTIONS = TIPOS_CASO.map((t) => ({ value: t.value, label: t.label }));

export function NovoCasoDialog({ open, onClose }: NovoCasoDialogProps) {
  const router = useRouter();
  const [titulo, setTitulo] = React.useState("");
  const [tipo, setTipo] = React.useState<TipoCaso | "">("");
  const [municipios, setMunicipios] = React.useState<string[]>([]);
  const [nome, setNome] = React.useState("");
  const [cnpj, setCnpj] = React.useState("");
  const [servidor, setServidor] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [erro, setErro] = React.useState<string | null>(null);

  function resetForm() {
    setTitulo("");
    setTipo("");
    setMunicipios([]);
    setNome("");
    setCnpj("");
    setServidor("");
    setErro(null);
  }

  function handleClose() {
    if (loading) return;
    resetForm();
    onClose();
  }

  function toggleMunicipio(slug: string) {
    setMunicipios((prev) =>
      prev.includes(slug) ? prev.filter((m) => m !== slug) : [...prev, slug],
    );
  }

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setErro(null);

    if (!titulo.trim()) {
      setErro("Informe o título do caso.");
      return;
    }
    if (!tipo) {
      setErro("Selecione a natureza do caso.");
      return;
    }
    if (municipios.length === 0) {
      setErro("Selecione ao menos um município a varrer.");
      return;
    }

    const alvos: CasoAlvos = {};
    if (tipo === "dano_erario_folha") {
      if (!servidor.trim()) {
        setErro("Informe o servidor (nome ou matrícula).");
        return;
      }
      alvos.servidor = servidor.trim();
    } else {
      if (!nome.trim() && !cnpj.trim()) {
        setErro("Informe ao menos o nome ou o CNPJ do alvo.");
        return;
      }
      if (nome.trim()) alvos.nome = nome.trim();
      if (cnpj.trim()) alvos.cnpj = cnpj.trim();
    }

    setLoading(true);
    try {
      const caso = await casosApi.criarCaso({ titulo: titulo.trim(), tipo, alvos, municipios });
      resetForm();
      onClose();
      // `/casos/[id]` nasce em W3 (plano §1) — cast necessário até a rota existir.
      router.push(`/casos/${caso.id}` as Route);
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "Não foi possível criar o caso.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Dialog open={open} onClose={handleClose} title="Novo caso">
      <form onSubmit={onSubmit} className="space-y-4" aria-busy={loading || undefined}>
        {erro && <ErrorState message={erro} />}

        <div>
          <label htmlFor="caso-titulo" className="mb-1 block text-[0.9375rem] font-medium">
            Título
          </label>
          <Input
            id="caso-titulo"
            value={titulo}
            onChange={(e) => setTitulo(e.target.value)}
            placeholder="Ex.: Dispensa de licitação — assessoria jurídica"
            required
            disabled={loading}
          />
        </div>

        <div>
          <label htmlFor="caso-tipo" className="mb-1 block text-[0.9375rem] font-medium">
            Natureza do caso
          </label>
          <Select
            id="caso-tipo"
            value={tipo}
            onChange={(e) => setTipo(e.target.value as TipoCaso)}
            placeholder="Selecione a natureza"
            options={TIPO_OPTIONS}
            required
            disabled={loading}
          />
        </div>

        <fieldset disabled={loading}>
          <legend className="mb-1 block text-[0.9375rem] font-medium">Municípios a varrer</legend>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {MUNICIPIOS_CASO.map((m) => (
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

        {tipo === "dano_erario_folha" ? (
          <div>
            <label htmlFor="caso-servidor" className="mb-1 block text-[0.9375rem] font-medium">
              Servidor (nome ou matrícula)
            </label>
            <Input
              id="caso-servidor"
              value={servidor}
              onChange={(e) => setServidor(e.target.value)}
              placeholder="Nome completo ou matrícula"
              disabled={loading}
            />
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <label htmlFor="caso-nome" className="mb-1 block text-[0.9375rem] font-medium">
                Nome do alvo
              </label>
              <Input
                id="caso-nome"
                value={nome}
                onChange={(e) => setNome(e.target.value)}
                placeholder="Razão social ou nome"
                disabled={loading}
              />
            </div>
            <div>
              <label htmlFor="caso-cnpj" className="mb-1 block text-[0.9375rem] font-medium">
                CNPJ do alvo
              </label>
              <Input
                id="caso-cnpj"
                value={cnpj}
                onChange={(e) => setCnpj(e.target.value)}
                placeholder="Um dos dois basta"
                disabled={loading}
              />
            </div>
          </div>
        )}

        <div className="flex justify-end gap-3 pt-2">
          <Button type="button" variant="secondary" onClick={handleClose} disabled={loading}>
            Cancelar
          </Button>
          <Button type="submit" loading={loading}>
            {loading ? "Criando…" : "Criar caso"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
