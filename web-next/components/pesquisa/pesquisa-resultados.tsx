"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, FileSearch } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { PesquisaEntidadeResponse, TipoEntidade } from "@/lib/api-types";
import { TableSkeleton } from "@/components/shared/skeleton";
import { ErrorState } from "@/components/shared/error-state";
import { EmptyState } from "@/components/shared/empty-state";
import { Badge } from "@/components/ui/badge";
import { GrupoResultados } from "./grupo-resultados";
import { GrupoFolha } from "./grupo-folha";

interface Props {
  slug: string;
  q: string;
  ano?: number;
  mes?: number;
}

const TIPO_LABEL: Record<TipoEntidade, string> = {
  cpf: "Detectei um CPF",
  cnpj: "Detectei um CNPJ",
  termo: "Pesquisando por termo",
};

function grupoVazio(data: PesquisaEntidadeResponse): boolean {
  return data.grupos.every((g) =>
    g.secao === "folha" ? (g.servidores ?? []).length === 0 : g.itens.length === 0,
  );
}

export function PesquisaResultados({ slug, q, ano, mes }: Props) {
  const [data, setData] = useState<PesquisaEntidadeResponse | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    api.pesquisar(slug, q, { ano, mes })
      .then((r) => {
        if (alive) setData(r);
      })
      .catch((e) => {
        if (alive)
          setError(e instanceof ApiError ? e : new ApiError(String(e), 0, null));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [slug, q, ano, mes]);

  if (loading) {
    return (
      <div aria-busy="true" className="space-y-3">
        <p className="flex items-center gap-2 text-[0.9375rem] text-muted-foreground">
          <FileSearch className="h-4 w-4 animate-pulse" aria-hidden="true" />
          Varrendo o portal, isso pode levar alguns segundos…
        </p>
        <TableSkeleton rows={4} />
        <TableSkeleton rows={4} />
      </div>
    );
  }

  if (error) {
    return (
      <ErrorState
        title="Falha na pesquisa"
        message={error.message}
        onRetry={() => window.location.reload()}
      />
    );
  }

  if (!data || data.grupos.length === 0 || grupoVazio(data)) {
    return (
      <div className="space-y-4">
        {data && data.avisos.length > 0 && <Avisos avisos={data.avisos} />}
        <EmptyState
          title="Nenhum resultado encontrado"
          description="Tente outro CNPJ, CPF, nome ou termo, ou confira se o período (ano/mês) está correto."
        />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge>{TIPO_LABEL[data.tipo]}</Badge>
        <span className="font-mono text-[0.9375rem] text-muted-foreground">{data.termo}</span>
        <span className="text-[0.9375rem] text-muted-foreground">em {data.municipio.nome}</span>
      </div>

      {data.avisos.length > 0 && <Avisos avisos={data.avisos} />}

      {data.grupos.map((g) =>
        g.secao === "folha" ? (
          <GrupoFolha key={g.secao} grupo={g} />
        ) : (
          <GrupoResultados key={g.secao} slug={slug} grupo={g} />
        ),
      )}
    </div>
  );
}

function Avisos({ avisos }: { avisos: string[] }) {
  return (
    <div className="rounded-md border border-warning bg-warning-tint p-3 text-[0.9375rem] text-foreground">
      <ul className="space-y-1">
        {avisos.map((a, i) => (
          <li key={i} className="flex gap-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden="true" />
            <span>{a}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
