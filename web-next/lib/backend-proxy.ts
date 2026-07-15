/** Encaminha uma requisição GET para o back FastAPI, traduzindo falha de
 *  conexão em uma resposta 502 com mensagem amigável em pt-BR, e estouro de
 *  tempo (B3: scraping pode levar ~30s+; teto de 60s) em 504. Repassa
 *  status e corpo JSON de erro do backend quando existirem (ex.: 502/503
 *  com {"error": "..."}). */
import { NextResponse } from "next/server";

const CONN_ERROR_MESSAGE =
  "Não foi possível conectar ao serviço de busca. Verifique se o servidor está ativo.";
const TIMEOUT_ERROR_MESSAGE = "A consulta demorou demais para responder. Tente novamente.";
const PROXY_TIMEOUT_MS = 60_000;

/** Credencial opcional para backend remoto protegido (ex.: "Basic dXN1YXJpbzpzZW5oYQ==").
 *  Sem BACKEND_AUTH no ambiente (dev local), nenhum header é enviado. */
function authHeaders(): Record<string, string> {
  const auth = process.env.BACKEND_AUTH;
  return auth ? { authorization: auth } : {};
}

export async function proxyBackend(
  path: string,
  timeoutMs: number = PROXY_TIMEOUT_MS,
): Promise<NextResponse> {
  const backend = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";
  let r: Response;
  try {
    r = await fetch(`${backend}${path}`, {
      cache: "no-store",
      headers: authHeaders(),
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch (e) {
    if (e instanceof Error && e.name === "TimeoutError") {
      return NextResponse.json({ error: TIMEOUT_ERROR_MESSAGE }, { status: 504 });
    }
    return NextResponse.json({ error: CONN_ERROR_MESSAGE }, { status: 502 });
  }
  const body = await r.text();
  return new NextResponse(body, {
    status: r.status,
    headers: {
      "content-type": r.headers.get("content-type") ?? "application/json",
    },
  });
}

/** Como proxyBackend, mas para respostas binárias (download de PDF de anexo,
 *  ou PDF/PNG de evidência de caso — W0-F1): repassa o corpo como buffer (não
 *  texto) e preserva Content-Type/Content-Disposition do back quando a
 *  resposta é `application/pdf` OU `image/*` (evidência de folha vem como
 *  screenshot PNG — api.py:687-704). O ramo de texto fica só p/ erro/JSON. Em
 *  erro, o back responde JSON ({"error":...}) — repassado como texto normalmente. */
export async function proxyBackendBinary(
  path: string,
  timeoutMs: number = PROXY_TIMEOUT_MS,
): Promise<NextResponse> {
  const backend = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";
  let r: Response;
  try {
    r = await fetch(`${backend}${path}`, {
      cache: "no-store",
      headers: authHeaders(),
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch (e) {
    if (e instanceof Error && e.name === "TimeoutError") {
      return NextResponse.json({ error: TIMEOUT_ERROR_MESSAGE }, { status: 504 });
    }
    return NextResponse.json({ error: CONN_ERROR_MESSAGE }, { status: 502 });
  }
  const contentType = r.headers.get("content-type") ?? "application/octet-stream";
  const isBinary = contentType.includes("application/pdf") || contentType.startsWith("image/");
  if (!r.ok || !isBinary) {
    const body = await r.text();
    return new NextResponse(body, {
      status: r.status,
      headers: { "content-type": contentType.includes("json") ? contentType : "application/json" },
    });
  }
  const buf = await r.arrayBuffer();
  const headers: Record<string, string> = { "content-type": contentType };
  const disposition = r.headers.get("content-disposition");
  if (disposition) headers["content-disposition"] = disposition;
  return new NextResponse(buf, { status: r.status, headers });
}

/** Encaminha uma requisição POST com corpo JSON para o back FastAPI. As
 *  ações longas de caso (`/pesquisar`, `/folha`, `/investigar`) respondem NA
 *  HORA com `{job_id}` — quem demora é o job, acompanhado via polling
 *  (`GET /api/jobs/{id}`). Por isso o timeout aqui é curto (30s bastam para
 *  o POST em si; plano §7 "Timeout do proxy Next para os POSTs"). */
const PROXY_POST_TIMEOUT_MS = 30_000;

export async function proxyBackendPost(
  path: string,
  body: unknown,
  timeoutMs: number = PROXY_POST_TIMEOUT_MS,
): Promise<NextResponse> {
  const backend = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";
  let r: Response;
  try {
    r = await fetch(`${backend}${path}`, {
      method: "POST",
      cache: "no-store",
      headers: { "content-type": "application/json", ...authHeaders() },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch (e) {
    if (e instanceof Error && e.name === "TimeoutError") {
      return NextResponse.json({ error: TIMEOUT_ERROR_MESSAGE }, { status: 504 });
    }
    return NextResponse.json({ error: CONN_ERROR_MESSAGE }, { status: 502 });
  }
  const respBody = await r.text();
  return new NextResponse(respBody, {
    status: r.status,
    headers: {
      "content-type": r.headers.get("content-type") ?? "application/json",
    },
  });
}
