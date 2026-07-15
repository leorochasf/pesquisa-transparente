import type { NextResponse } from "next/server";
import { proxyBackend } from "@/lib/backend-proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(
  req: Request,
  {
    params,
  }: { params: Promise<{ slug: string; secao: string }> },
): Promise<NextResponse> {
  const { slug, secao } = await params;
  const incoming = new URL(req.url);
  const qs = incoming.searchParams.toString();
  return proxyBackend(`/api/buscar/${slug}/${secao}${qs ? `?${qs}` : ""}`);
}
