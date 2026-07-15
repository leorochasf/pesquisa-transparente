"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";
import { Select } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useMunicipios } from "@/hooks/use-municipios";
import { ErrorState } from "@/components/shared/error-state";
import { Skeleton } from "@/components/shared/skeleton";
import { ChevronDown } from "lucide-react";

interface Props {
  municipio?: string;
  q?: string;
  ano?: number;
  mes?: number;
}

export function PesquisaForm({ municipio, q, ano, mes }: Props) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const { data: municipios, loading, error } = useMunicipios();
  const [municipioSel, setMunicipioSel] = useState(municipio ?? "");

  useEffect(() => {
    setMunicipioSel(municipio ?? "");
  }, [municipio]);

  function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const m = String(form.get("municipio") ?? "");
    const termo = String(form.get("q") ?? "");
    const anoV = String(form.get("ano") ?? "");
    const mesV = String(form.get("mes") ?? "");

    const sp = new URLSearchParams();
    if (m) sp.set("m", m);
    if (termo) sp.set("q", termo);
    if (anoV) sp.set("ano", anoV);
    if (mesV) sp.set("mes", mesV);
    const qs = sp.toString();
    startTransition(() => {
      router.push(qs ? `/pesquisar?${qs}` : "/pesquisar");
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
    <form onSubmit={onSubmit} className="space-y-4" aria-label="Pesquisar por entidade">
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
            onChange={(e) => setMunicipioSel(e.target.value)}
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
        <label htmlFor="q" className="mb-1 block text-[0.9375rem] font-medium">
          O que você procura?
        </label>
        <Input
          id="q"
          name="q"
          defaultValue={q ?? ""}
          placeholder="CNPJ, CPF, nome do servidor ou termo"
          required
        />
        <p className="mt-1 text-xs text-muted-foreground">
          Ex.: um CNPJ de fornecedor, o nome de um servidor, ou uma palavra do objeto de um contrato.
        </p>
      </div>
      <details className="group rounded-sm border border-border p-3">
        <summary className="flex cursor-pointer list-none items-center gap-1.5 text-[0.9375rem] font-medium">
          <ChevronDown
            className="h-4 w-4 text-muted-foreground transition-transform duration-[var(--dur-base)] ease-[var(--ease-standard)] group-open:rotate-180"
            aria-hidden="true"
          />
          Período (usado apenas na busca da folha de pagamento)
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
              defaultValue={ano ?? ""}
              placeholder="ex.: 2026"
            />
          </div>
          <div>
            <label htmlFor="mes" className="mb-1 block text-xs font-medium text-muted-foreground">
              Mês
            </label>
            <Input
              id="mes"
              name="mes"
              type="number"
              min={1}
              max={12}
              defaultValue={mes ?? ""}
              placeholder="ex.: 6"
            />
          </div>
        </div>
      </details>
      <Button type="submit" loading={isPending}>
        {isPending ? "Buscando…" : "Pesquisar"}
      </Button>
    </form>
  );
}
