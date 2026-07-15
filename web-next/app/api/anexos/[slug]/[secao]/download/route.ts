import type { NextResponse } from "next/server";
import { proxyBackendBinary } from "@/lib/backend-proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(
  req: Request,
  { params }: { params: Promise<{ slug: string; secao: string }> },
): Promise<NextResponse> {
  const { slug, secao } = await params;
  const incoming = new URL(req.url);
  const qs = incoming.searchParams.toString();
  return proxyBackendBinary(`/api/anexos/${slug}/${secao}/download${qs ? `?${qs}` : ""}`, 120_000);
}
