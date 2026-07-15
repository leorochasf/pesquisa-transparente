import type { NextResponse } from "next/server";
import { proxyBackendBinary } from "@/lib/backend-proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string; ev: string }> },
): Promise<NextResponse> {
  const { id, ev } = await params;
  return proxyBackendBinary(`/api/casos/${id}/evidencias/${ev}/arquivo`);
}
