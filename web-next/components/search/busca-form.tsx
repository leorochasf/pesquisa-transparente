"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";
import { Select } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useMunicipios } from "@/hooks/use-municipios";
import { useSecoes } from "@/hooks/use-secoes";
import { ErrorState } from "@/components/shared/error-state";
import { Skeleton } from "@/components/shared/skeleton";
import { ChevronDown } from "lucide-react";
import type { FiltrosBusca } from "@/lib/api-types";
import { composeSecaoOptions } from "@/lib/secoes";

interface Props {
  municipio?: string;
  secao?: string;
  filtros?: FiltrosBusca;
}

export function BuscaForm({ municipio, secao, filtros }: Props) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const { data: municipios, loading, error } = useMunicipios();
  const [municipioSel, setMunicipioSel] = useState(municipio ?? "");
  const [secaoSel, setSecaoSel] = useState(secao ?? "");
  const { data: secoes } = useSecoes(municipioSel || null);
  const secaoOptions = composeSecaoOptions(secoes, secaoSel);

  // Mantem o estado controlado em sincronia quando a URL muda (ex.: submit).
  useEffect(() => {
    setMunicipioSel(municipio ?? "");
  }, [municipio]);

  useEffect(() => {
    setSecaoSel(secao ?? "");
  }, [secao]);

  function onMunicipioChange(e: React.ChangeEvent<HTMLSelectElement>) {
    setMunicipioSel(e.target.value);
    setSecaoSel("");
  }

  function onSecaoChange(e: React.ChangeEvent<HTMLSelectElement>) {
    setSecaoSel(e.target.value);
  }

  function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const m = String(form.get("municipio") ?? "");
    const s = String(form.get("secao") ?? "");
    const ano = String(form.get("ano") ?? "");
    const cnpj = String(form.get("cnpj") ?? "");

    const sp = new URLSearchParams();
    if (m) sp.set("m", m);
    if (s) sp.set("s", s);
    if (ano) sp.set("f[ano]", ano);
    if (cnpj) sp.set("f[cnpj]", cnpj);
    const qs = sp.toString();
    startTransition(() => {
      router.push(qs ? `/buscar?${qs}` : "/buscar");
    });
  }

  if (error) {
    return (
      <ErrorState
        title="Falha ao carregar municípios"
        message={error.message}
        onRetry={() => router.refresh()}
      />
    );
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4" aria-label="Filtros de busca">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="municipio" className="mb-1 block text-[0.9375rem] font-medium">
            Município
          </label>
          {loading ? (
            <Skeleton className="h-[38px] w-full" />
          ) : (
            <Select
              id="municipio"
              name="municipio"
              value={municipioSel}
              onChange={onMunicipioChange}
              placeholder="Selecione um município"
              options={(municipios ?? []).map((m) => ({
                value: m.slug,
                label: m.nome,
              }))}
              required
            />
          )}
        </div>
        <div>
          <label htmlFor="secao" className="mb-1 block text-[0.9375rem] font-medium">
            Seção
          </label>
          <Select
            id="secao"
            name="secao"
            value={secaoSel}
            onChange={onSecaoChange}
            placeholder={municipioSel ? "Selecione uma seção" : "Escolha um município primeiro"}
            options={secaoOptions.map((s) => ({ value: s, label: s }))}
            disabled={!municipioSel || !secaoOptions.length}
            required
          />
        </div>
      </div>
      <details className="group rounded-sm border border-border p-3">
        <summary className="flex cursor-pointer list-none items-center gap-1.5 text-[0.9375rem] font-medium">
          <ChevronDown
            className="h-4 w-4 text-muted-foreground transition-transform duration-[var(--dur-base)] ease-[var(--ease-standard)] group-open:rotate-180"
            aria-hidden="true"
          />
          Filtros avançados
        </summary>
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label htmlFor="ano" className="mb-1 block text-xs font-medium text-muted-foreground">
              Ano
            </label>
            <Input
              id="ano"
              name="ano"
              type="number"
              min={2000}
              max={2100}
              defaultValue={filtros?.ano ?? ""}
              placeholder="ex.: 2024"
            />
          </div>
          <div>
            <label htmlFor="cnpj" className="mb-1 block text-xs font-medium text-muted-foreground">
              CNPJ
            </label>
            <Input
              id="cnpj"
              name="cnpj"
              defaultValue={filtros?.cnpj ?? ""}
              placeholder="00.000.000/0000-00"
            />
          </div>
        </div>
      </details>
      <Button type="submit" loading={isPending}>
        {isPending ? "Buscando…" : "Buscar"}
      </Button>
    </form>
  );
}