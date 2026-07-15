import type { NextResponse } from "next/server";
import { proxyBackend, proxyBackendBinary } from "@/lib/backend-proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** `GET /api/casos/{id}/relatorio` — sem `?formato`, repassa `text/markdown`
 *  (proxyBackend passa o content-type adiante sem exigir JSON). Com
 *  `?formato=pdf`, usa proxyBackendBinary (hoje pode responder 501,
 *  `RelatorioPdfIndisponivel` — o proxy repassa o status/erro tal-qual,
 *  plano §7). */
export async function GET(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
): Promise<NextResponse> {
  const { id } = await params;
  const incoming = new URL(req.url);
  const formato = incoming.searchParams.get("formato");
  if (formato === "pdf") {
    return proxyBackendBinary(`/api/casos/${id}/relatorio?formato=pdf`);
  }
  return proxyBackend(`/api/casos/${id}/relatorio`);
}
