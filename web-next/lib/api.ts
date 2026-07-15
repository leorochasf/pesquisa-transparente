/** Cliente HTTP para os route handlers do Next.js (que proxiam para FastAPI).
 *
 * Como o Next.js e o FastAPI estao em processos separados em dev, o front
 * chama SEUS proprios /api/* via este wrapper. Quando virar producao,
 * NEXT_PUBLIC_API_BASE pode apontar direto para o back sem o proxy.
 */

import type {
  AnexoOut,
  BuscaResponse,
  FiltrosBusca,
  MunicipioOut,
  PesquisaEntidadeResponse,
  RefRegistro,
  SecoesResponse,
} from "./api-types";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(message: string, status: number, detail: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

// B4: no browser, BASE e SEMPRE relativo ("") — mesma origem, funciona em
// qualquer host que sirva o site (produção pode responder por múltiplos
// hosts, ex.: domínio custom + URL longa da Vercel). NEXT_PUBLIC_API_BASE só
// vale no ramo servidor (SSR self-referencial, necessário em serverless onde
// 127.0.0.1 não resolve para o próprio processo); sem a env, cai no
// 127.0.0.1:PORT (setada pelo `next dev`/`next start` quando 3000 esta
// ocupada e ele sobe em 3001+).
const BASE =
  typeof window === "undefined"
    ? (process.env.NEXT_PUBLIC_API_BASE ?? `http://127.0.0.1:${process.env.PORT ?? "3000"}`)
    : "";

async function http<T>(path: string): Promise<T> {
  const url = `${BASE}${path}`;
  const res = await fetch(url, {
    // SSR: nao cachear; client: revalidar via SWR depois.
    cache: "no-store",
  });
  const body = await res.text();
  const data: unknown = body ? safeJson(body) : null;
  if (!res.ok) {
    throw new ApiError(extractErrorMessage(data), res.status, data);
  }
  return data as T;
}

function safeJson(s: string): unknown {
  try {
    return JSON.parse(s);
  } catch {
    return null;
  }
}

/** Extrai mensagem amigável do corpo de erro. Prioriza o campo `error`
 *  (contrato novo do backend: 502/503 com {"error": "<mensagem pt-BR>"}),
 *  depois `detail` (FastAPI default). Nunca expõe statusText cru. */
function extractErrorMessage(data: unknown): string {
  if (typeof data === "object" && data !== null) {
    const obj = data as Record<string, unknown>;
    if (typeof obj.error === "string" && obj.error) return obj.error;
    if (obj.detail != null) return String(obj.detail);
  }
  return "Ocorreu um erro inesperado ao comunicar com o serviço de busca.";
}

export const api = {
  municipios: () => http<MunicipioOut[]>("/api/municipios"),
  secoes: (slug: string) => http<SecoesResponse>(`/api/secoes/${slug}`),
  buscar: (
    slug: string,
    secao: string,
    filtros?: FiltrosBusca,
  ): Promise<BuscaResponse> => {
    const params = new URLSearchParams();
    if (filtros) {
      for (const [k, v] of Object.entries(filtros)) {
        if (v != null && v !== "") params.set(k, String(v));
      }
    }
    const qs = params.toString();
    return http<BuscaResponse>(
      `/api/buscar/${slug}/${secao}${qs ? `?${qs}` : ""}`,
    );
  },
  pesquisar: (
    slug: string,
    q: string,
    periodo?: { ano?: number; mes?: number },
  ): Promise<PesquisaEntidadeResponse> => {
    const params = new URLSearchParams();
    params.set("q", q);
    if (periodo?.ano != null) params.set("ano", String(periodo.ano));
    if (periodo?.mes != null) params.set("mes", String(periodo.mes));
    return http<PesquisaEntidadeResponse>(
      `/api/pesquisar/${slug}?${params.toString()}`,
    );
  },
  listarAnexos: (
    slug: string,
    secao: string,
    registro: RefRegistro,
  ): Promise<AnexoOut[]> => {
    const params = new URLSearchParams();
    if (registro.id) params.set("id", registro.id);
    if (registro.numero) params.set("numero", registro.numero);
    if (registro.ano) params.set("ano", registro.ano);
    return http<AnexoOut[]>(`/api/anexos/${slug}/${secao}?${params.toString()}`);
  },
};

/** Monta a URL de download de 1 anexo — usada diretamente em `<a href>` para
 *  o navegador baixar o PDF (não passa pelo wrapper JSON `http()`). */
export function anexoDownloadUrl(slug: string, secao: string, ref: string): string {
  return `${BASE}/api/anexos/${slug}/${secao}/download?ref=${encodeURIComponent(ref)}`;
}