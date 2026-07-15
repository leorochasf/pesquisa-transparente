"use client";

import * as React from "react";
import type { Route } from "next";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { TableSkeleton } from "@/components/shared/skeleton";
import { useCasos } from "@/hooks/use-casos";
import { NovoCasoDialog } from "@/components/casos/novo-caso-dialog";
import { rotuloTipo, MUNICIPIOS_CASO } from "@/components/casos/caso-tipo";
import type { CasoResumo } from "@/lib/casos-types";

const NOME_MUNICIPIO = new Map<string, string>(MUNICIPIOS_CASO.map((m) => [m.value, m.label]));

function rotuloMunicipio(slug: string): string {
  return NOME_MUNICIPIO.get(slug) ?? slug;
}

function formatarData(epochSegundos: number): string {
  return new Date(epochSegundos * 1000).toLocaleDateString("pt-BR");
}

export function HomeCasosRecentes() {
  const router = useRouter();
  const { data, error, loading, refetch } = useCasos();
  const [dialogAberto, setDialogAberto] = React.useState(false);

  function abrirCaso(id: string) {
    router.push(`/casos/${id}` as Route);
  }

  const recentes = data ? [...data].sort((a, b) => b.atualizado_em - a.atualizado_em).slice(0, 4) : [];

  return (
    <div>
      <div className="mb-6 flex items-center justify-between gap-3">
        <h2 className="text-[1.3125rem] font-semibold leading-[1.3]">Casos</h2>
        <Button type="button" onClick={() => setDialogAberto(true)}>
          Novo caso
        </Button>
      </div>

      {loading ? (
        <TableSkeleton rows={4} cols={4} />
      ) : error ? (
        <ErrorState
          title="Não foi possível carregar os casos"
          message={error.message}
          onRetry={() => refetch()}
        />
      ) : !data || data.length === 0 ? (
        <EmptyState
          title="Nenhum caso ainda"
          description='Um caso reúne os alvos, as pesquisas, as evidências e o dossiê final de uma investigação. Abra o primeiro no botão "Novo caso" acima.'
        />
      ) : (
        <>
          <Table>
            <caption className="sr-only">
              Casos recentes ({recentes.length} de {data.length})
            </caption>
            <THead>
              <TR className="hover:bg-card">
                <TH>Título</TH>
                <TH>Tipo</TH>
                <TH>Municípios</TH>
                <TH className="text-right">Atualizado em</TH>
              </TR>
            </THead>
            <TBody>
              {recentes.map((caso: CasoResumo) => (
                <TR key={caso.id} className="cursor-pointer" onClick={() => abrirCaso(caso.id)}>
                  <TD>
                    <a
                      href={`/casos/${caso.id}`}
                      onClick={(e) => e.stopPropagation()}
                      className="text-primary underline underline-offset-2 hover:text-primary-hover"
                    >
                      {caso.titulo}
                    </a>
                  </TD>
                  <TD>
                    <Badge variant="secondary">{rotuloTipo(caso.tipo)}</Badge>
                  </TD>
                  <TD>
                    <div className="flex flex-wrap gap-1">
                      {caso.municipios.map((slug) => (
                        <Badge key={slug} variant="secondary">
                          {rotuloMunicipio(slug)}
                        </Badge>
                      ))}
                    </div>
                  </TD>
                  <TD className="text-right font-mono tabular-nums">
                    {formatarData(caso.atualizado_em)}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          {data.length > 0 && (
            <p className="mt-4">
              <Link href="/casos" className="text-primary underline underline-offset-2 hover:text-primary-hover">
                Ver todos os casos ({data.length})
              </Link>
            </p>
          )}
        </>
      )}

      <NovoCasoDialog
        open={dialogAberto}
        onClose={() => {
          setDialogAberto(false);
          refetch();
        }}
      />
    </div>
  );
}
