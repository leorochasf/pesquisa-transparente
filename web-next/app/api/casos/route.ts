import { NextResponse } from "next/server";
import { proxyBackend, proxyBackendPost } from "@/lib/backend-proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(): Promise<NextResponse> {
  return proxyBackend("/api/casos");
}

export async function POST(req: Request): Promise<NextResponse> {
  const body = await req.json();
  return proxyBackendPost("/api/casos", body);
}
