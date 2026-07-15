"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { BuscaResponse, FiltrosBusca } from "@/lib/api-types";
import { TableSkeleton } from "@/components/shared/skeleton";
import { ErrorState } from "@/components/shared/error-state";
import { EmptyState } from "@/components/shared/empty-state";
import { ResultadoTable } from "./resultado-table";

interface Props {
  slug: string;
  secao: string;
  filtros?: FiltrosBusca;
}

export function ResultadosCliente({ slug, secao, filtros }: Props) {
  const [data, setData] = useState<BuscaResponse | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    api.buscar(slug, secao, filtros)
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
  }, [slug, secao, JSON.stringify(filtros)]);

  if (loading) {
    return (
      <div aria-busy="true">
        <TableSkeleton />
      </div>
    );
  }
  if (error) {
    return (
      <ErrorState
        title="Falha na busca"
        message={error.message}
        onRetry={() => routerRefresh()}
      />
    );
  }
  if (!data || data.items.length === 0) {
    return (
      <EmptyState
        title="Nenhum resultado para estes filtros"
        description="Tente remover o filtro de ano, revisar o CNPJ informado ou escolher outra seção."
      />
    );
  }
  return (
    <ResultadoTable
      items={data.items}
      sourceUrl={data.source_url}
      cached={data.cached}
    />
  );
}

function routerRefresh() {
  // Forca re-fetch do cliente (simplificado: reload da pagina).
  if (typeof window !== "undefined") window.location.reload();
}