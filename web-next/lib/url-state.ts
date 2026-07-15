/** Serializa filtros em searchParams e vice-versa.
 *  Mantem a URL compartilhavel (ex.: /?m=senadorcanedo&s=licitacoes&ano=2024). */

import type { FiltrosBusca } from "./api-types";

const FILTER_KEYS: (keyof FiltrosBusca)[] = [
  "ano",
  "cnpj",
  "modalidade",
  "numero",
  "credor",
];

export type SearchState = {
  municipio?: string;
  secao?: string;
  filtros?: FiltrosBusca;
};

export function readSearchParams(sp: URLSearchParams): SearchState {
  const municipio = sp.get("m") ?? undefined;
  const secao = sp.get("s") ?? undefined;
  const filtros: FiltrosBusca = {};
  for (const k of FILTER_KEYS) {
    const v = sp.get(`f[${k}]`);
    if (v) {
      if (k === "ano") {
        const n = Number(v);
        if (Number.isFinite(n)) filtros.ano = n;
      } else {
        filtros[k] = v;
      }
    }
  }
  return {
    municipio,
    secao,
    filtros: Object.keys(filtros).length ? filtros : undefined,
  };
}

export function writeSearchParams(state: SearchState): URLSearchParams {
  const sp = new URLSearchParams();
  if (state.municipio) sp.set("m", state.municipio);
  if (state.secao) sp.set("s", state.secao);
  if (state.filtros) {
    for (const k of FILTER_KEYS) {
      const v = state.filtros[k];
      if (v != null && v !== "") sp.set(`f[${k}]`, String(v));
    }
  }
  return sp;
}