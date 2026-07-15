import type { Metadata } from "next";
import { Suspense } from "react";
import { Dossie } from "@/components/casos/dossie";
import { Skeleton, TableSkeleton } from "@/components/shared/skeleton";

interface Props {
  params: Promise<{ id: string }>;
}

export const metadata: Metadata = {
  title: "Dossiê do caso · Transparência Goiás",
  description: "Cabeçalho, ações, acompanhamento, itens, lacunas e relatório de um caso.",
};

function DossieSkeleton() {
  return (
    <div className="space-y-8">
      <div className="space-y-3 border-b border-border pb-6">
        <Skeleton className="h-7 w-2/3" />
        <Skeleton className="h-4 w-1/3" />
      </div>
      <TableSkeleton rows={4} cols={4} />
    </div>
  );
}

export default async function CasoPage({ params }: Props) {
  const { id } = await params;
  return (
    <div className="mx-auto max-w-6xl px-6 py-10">
      <Suspense fallback={<DossieSkeleton />}>
        <Dossie casoId={id} />
      </Suspense>
    </div>
  );
}
