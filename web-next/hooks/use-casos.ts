"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError } from "@/lib/api";
import { casosApi } from "@/lib/casos-api";
import type { CasoDetalhe, CasoResumo } from "@/lib/casos-types";

/** Hook de lista de casos. Sem SWR, mesmo padrão de `use-municipios.ts`. */
export function useCasos() {
  const [data, setData] = useState<CasoResumo[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);

  const refetch = useCallback(() => {
    setLoading(true);
    setError(null);
    return casosApi
      .listarCasos()
      .then((casos) => {
        setData(casos);
      })
      .catch((e) => {
        setError(e instanceof ApiError ? e : new ApiError(String(e), 0, null));
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    casosApi
      .listarCasos()
      .then((casos) => {
        if (alive) setData(casos);
      })
      .catch((e) => {
        if (alive) setError(e instanceof ApiError ? e : new ApiError(String(e), 0, null));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  return { data, error, loading, refetch };
}

/** Hook de detalhe de 1 caso (dossiê). W3 importa para montar `/casos/[id]`. */
export function useCaso(id: string | null) {
  const [data, setData] = useState<CasoDetalhe | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);

  const refetch = useCallback(() => {
    if (!id) return Promise.resolve();
    setLoading(true);
    setError(null);
    return casosApi
      .obterCaso(id)
      .then((caso) => {
        setData(caso);
      })
      .catch((e) => {
        setError(e instanceof ApiError ? e : new ApiError(String(e), 0, null));
      })
      .finally(() => {
        setLoading(false);
      });
  }, [id]);

  useEffect(() => {
    if (!id) {
      setData(null);
      setLoading(false);
      return;
    }
    let alive = true;
    setLoading(true);
    setError(null);
    casosApi
      .obterCaso(id)
      .then((caso) => {
        if (alive) setData(caso);
      })
      .catch((e) => {
        if (alive) setError(e instanceof ApiError ? e : new ApiError(String(e), 0, null));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [id]);

  return { data, error, loading, refetch };
}
