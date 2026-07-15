import type { Metadata } from "next";
import { BuscaForm } from "@/components/search/busca-form";
import { ResultadosCliente } from "@/components/search/resultados-cliente";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/shared/empty-state";
import { readSearchParams } from "@/lib/url-state";

interface PageProps {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}

export const metadata: Metadata = {
  title: "Buscar por seção · Transparência Goiás",
  description:
    "Percorra licitações, contratos, dispensas e despesas de um município goiano, seção por seção, direto do portal oficial — com o PDF de cada documento a um clique.",
};

export default async function BuscarPage({ searchParams }: PageProps) {
  const sp = await searchParams;
  const usp = new URLSearchParams();
  for (const [k, v] of Object.entries(sp)) {
    if (typeof v === "string") usp.set(k, v);
    else if (Array.isArray(v)) usp.set(k, v.join(","));
  }
  const state = readSearchParams(usp);

  return (
    <div className="mx-auto max-w-6xl px-6 py-10">
      <header className="mb-8 border-b border-border pb-8">
        <h1 className="text-[1.625rem] font-semibold leading-[1.25] tracking-[-0.01em] sm:text-[1.9rem]">
          Buscar por seção
        </h1>
        <p className="mt-2 max-w-2xl text-[0.9375rem] text-muted-foreground">
          Escolha um município e uma seção — licitações, contratos, dispensas, despesas — e o
          app traz os registros do portal oficial, com o PDF a um clique. Para procurar um CNPJ
          ou servidor específico, use a pesquisa por entidade.
        </p>
      </header>

      <Card className="mb-10">
        <CardContent className="p-6">
          <BuscaForm
            municipio={state.municipio}
            secao={state.secao}
            filtros={state.filtros}
          />
        </CardContent>
      </Card>

      {state.municipio && state.secao ? (
        <ResultadosCliente
          slug={state.municipio}
          secao={state.secao}
          filtros={state.filtros}
        />
      ) : (
        <EmptyState
          title="Comece uma busca"
          description="Escolha um município e uma seção acima; refine por ano ou CNPJ."
        />
      )}
    </div>
  );
}
