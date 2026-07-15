import type { NextResponse } from "next/server";
import { proxyBackendPost } from "@/lib/backend-proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
): Promise<NextResponse> {
  const { id } = await params;
  const body = await req.json();
  return proxyBackendPost(`/api/casos/${id}/anotacoes`, body);
}
