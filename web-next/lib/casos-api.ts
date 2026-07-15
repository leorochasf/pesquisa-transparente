/** Cliente HTTP do modo Caso/Dossiê — chama os route handlers em
 *  `app/api/casos/**`/`app/api/jobs/**` (que proxiam para o FastAPI). Mesmo
 *  padrão de `lib/api.ts` (wrapper `http<T>` JSON-only + `ApiError`), mas com
 *  funções POST (que `lib/api.ts` não tem — plano §3). */

import { ApiError } from "./api";
import type {
  AnotacaoBody,
  AnotacaoCaso,
  CasoDetalhe,
  CasoResumo,
  CriarCasoBody,
  FolhaCasoBody,
  InvestigarCasoBody,
  Job,
  PesquisarCasoBody,
} from "./casos-types";

// No browser, BASE e SEMPRE relativo ("") — mesma origem, funciona em
// qualquer host que sirva o site. NEXT_PUBLIC_API_BASE só vale no ramo
// servidor (SSR self-referencial em serverless); sem a env, cai no
// 127.0.0.1:PORT (mesmo padrão de lib/api.ts).
const BASE =
  typeof window === "undefined"
    ? (process.env.NEXT_PUBLIC_API_BASE ?? `http://127.0.0.1:${process.env.PORT ?? "3000"}`)
    : "";

function safeJson(s: string): unknown {
  try {
    return JSON.parse(s);
  } catch {
    return null;
  }
}

function extractErrorMessage(data: unknown): string {
  if (typeof data === "object" && data !== null) {
    const obj = data as Record<string, unknown>;
    if (typeof obj.error === "string" && obj.error) return obj.error;
    if (obj.detail != null) return String(obj.detail);
  }
  return "Ocorreu um erro inesperado ao comunicar com o serviço de busca.";
}

async function http<T>(path: string): Promise<T> {
  const url = `${BASE}${path}`;
  const res = await fetch(url, { cache: "no-store" });
  const body = await res.text();
  const data: unknown = body ? safeJson(body) : null;
  if (!res.ok) {
    throw new ApiError(extractErrorMessage(data), res.status, data);
  }
  return data as T;
}

async function httpPost<T>(path: string, payload: unknown): Promise<T> {
  const url = `${BASE}${path}`;
  const res = await fetch(url, {
    method: "POST",
    cache: "no-store",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await res.text();
  const data: unknown = body ? safeJson(body) : null;
  if (!res.ok) {
    throw new ApiError(extractErrorMessage(data), res.status, data);
  }
  return data as T;
}

export const casosApi = {
  listarCasos: (): Promise<CasoResumo[]> => http<CasoResumo[]>("/api/casos"),
  criarCaso: (body: CriarCasoBody): Promise<CasoDetalhe> =>
    httpPost<CasoDetalhe>("/api/casos", body),
  obterCaso: (id: string): Promise<CasoDetalhe> => http<CasoDetalhe>(`/api/casos/${id}`),
  pesquisarCaso: (id: string, body: PesquisarCasoBody): Promise<{ job_id: string }> =>
    httpPost<{ job_id: string }>(`/api/casos/${id}/pesquisar`, body),
  folhaCaso: (id: string, body: FolhaCasoBody): Promise<{ job_id: string }> =>
    httpPost<{ job_id: string }>(`/api/casos/${id}/folha`, body),
  investigarCaso: (id: string, body: InvestigarCasoBody): Promise<{ job_id: string }> =>
    httpPost<{ job_id: string }>(`/api/casos/${id}/investigar`, body),
  anotarCaso: (id: string, body: AnotacaoBody): Promise<AnotacaoCaso> =>
    httpPost<AnotacaoCaso>(`/api/casos/${id}/anotacoes`, body),
  obterJob: (jobId: string): Promise<Job> => http<Job>(`/api/jobs/${jobId}`),
};

/** W0-F7: o relatório é `text/markdown`, não JSON — `http<T>` faria
 *  `JSON.parse` e devolveria `null`. Função dedicada: fetch + `res.text()`. */
export async function obterRelatorioMd(casoId: string): Promise<string> {
  const url = `${BASE}/api/casos/${casoId}/relatorio`;
  const res = await fetch(url, { cache: "no-store" });
  const body = await res.text();
  if (!res.ok) {
    throw new ApiError(extractErrorMessage(safeJson(body)), res.status, safeJson(body));
  }
  return body;
}

/** Monta a URL de download de 1 evidência (PNG/PDF) — usada em `<a href>` ou
 *  botão "Baixar"; passa pelo proxy Next server-side (nunca chama o backend
 *  direto do browser, plano §6.4). */
export function evidenciaArquivoUrl(casoId: string, evidenciaId: string): string {
  return `${BASE}/api/casos/${casoId}/evidencias/${evidenciaId}/arquivo`;
}

/** Monta a URL do relatório — `formato="pdf"` só p/ o `<a>` de download
 *  (hoje pode responder 501, plano §7 "Export PDF"). Sem `formato`, é o
 *  markdown consumido via `obterRelatorioMd`. */
export function relatorioUrl(casoId: string, formato?: "pdf"): string {
  const qs = formato ? `?formato=${formato}` : "";
  return `${BASE}/api/casos/${casoId}/relatorio${qs}`;
}
