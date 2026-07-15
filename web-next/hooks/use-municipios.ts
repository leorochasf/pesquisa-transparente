"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { MunicipioOut } from "@/lib/api-types";

/** Hook simples para listar municipios. Sem SWR para reduzir deps. */
export function useMunicipios() {
  const [data, setData] = useState<MunicipioOut[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api.municipios()
      .then((m) => {
        if (alive) setData(m);
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

  return { data, error, loading };
}