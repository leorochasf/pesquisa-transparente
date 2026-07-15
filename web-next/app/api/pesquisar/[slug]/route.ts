import type { NextResponse } from "next/server";
import { proxyBackend } from "@/lib/backend-proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(
  req: Request,
  { params }: { params: Promise<{ slug: string }> },
): Promise<NextResponse> {
  const { slug } = await params;
  const incoming = new URL(req.url);
  const qs = incoming.searchParams.toString();
  // Medido ao vivo (verificação Ui90cB65-33): pesquisa por CNPJ em Senador
  // Canedo varrendo contratos+licitacoes+dispensas levou ~185s no backend —
  // acima dos ~120s sugeridos no brief. Margem ampliada para não estourar
  // 504 em cenários reais (varredura sequencial de múltiplas seções).
  return proxyBackend(`/api/pesquisar/${slug}${qs ? `?${qs}` : ""}`, 240_000);
}
