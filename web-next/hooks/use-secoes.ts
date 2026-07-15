"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";

/** Hook para listar secoes de um municipio. */
export function useSecoes(slug: string | null) {
  const [data, setData] = useState<string[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!slug) {
      setData(null);
      return;
    }
    let alive = true;
    setLoading(true);
    api.secoes(slug)
      .then((r) => {
        if (alive) setData(r.secoes);
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
  }, [slug]);

  return { data, error, loading };
}