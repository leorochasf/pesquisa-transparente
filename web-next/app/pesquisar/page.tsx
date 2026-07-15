import type { Metadata } from "next";
import { PesquisaForm } from "@/components/pesquisa/pesquisa-form";
import { PesquisaResultados } from "@/components/pesquisa/pesquisa-resultados";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/shared/empty-state";

interface PageProps {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}

export const metadata: Metadata = {
  title: "Pesquisar por entidade · Transparência Goiás",
  description:
    "Pesquise um CNPJ de fornecedor, o nome de um servidor ou um termo num município e veja tudo agrupado por seção.",
};

function param(sp: Record<string, string | string[] | undefined>, key: string): string | undefined {
  const v = sp[key];
  return typeof v === "string" ? v : Array.isArray(v) ? v[0] : undefined;
}

export default async function PesquisarPage({ searchParams }: PageProps) {
  const sp = await searchParams;
  const municipio = param(sp, "m");
  const q = param(sp, "q");
  const anoRaw = param(sp, "ano");
  const mesRaw = param(sp, "mes");
  const ano = anoRaw ? Number(anoRaw) : undefined;
  const mes = mesRaw ? Number(mesRaw) : undefined;

  return (
    <div className="mx-auto max-w-6xl px-6 py-10">
      <header className="mb-8 border-b border-border pb-8">
        <h1 className="text-[1.625rem] font-semibold leading-[1.25] tracking-[-0.01em] sm:text-[1.9rem]">
          Pesquisar por entidade
        </h1>
        <p className="mt-2 max-w-2xl text-[0.9375rem] text-muted-foreground">
          Escolha um município e digite um CNPJ de fornecedor, um CPF ou nome de servidor, ou
          um termo. O app varre o portal e traz tudo, agrupado por seção.
        </p>
      </header>

      <Card className="mb-10">
        <CardContent className="p-6">
          <PesquisaForm municipio={municipio} q={q} ano={ano} mes={mes} />
        </CardContent>
      </Card>

      {municipio && q ? (
        <PesquisaResultados slug={municipio} q={q} ano={ano} mes={mes} />
      ) : (
        <EmptyState
          title="Nenhuma pesquisa feita ainda"
          description="Escolha um município e digite o que você procura acima."
        />
      )}
    </div>
  );
}
