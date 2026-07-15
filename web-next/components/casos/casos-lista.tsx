"use client";

import * as React from "react";
import type { Route } from "next";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { TableSkeleton } from "@/components/shared/skeleton";
import { useCasos } from "@/hooks/use-casos";
import { rotuloTipo, MUNICIPIOS_CASO } from "@/components/casos/caso-tipo";
import { NovoCasoDialog } from "@/components/casos/novo-caso-dialog";
import type { CasoResumo } from "@/lib/casos-types";

const NOME_MUNICIPIO = new Map<string, string>(MUNICIPIOS_CASO.map((m) => [m.value, m.label]));

function rotuloMunicipio(slug: string): string {
  return NOME_MUNICIPIO.get(slug) ?? slug;
}

function alvoResumo(caso: CasoResumo): string {
  const { nome, cnpj, servidor } = caso.alvos;
  const partes = [nome, cnpj, servidor].filter((v): v is string => Boolean(v));
  return partes.join(" · ");
}

function formatarData(epochSegundos: number): string {
  return new Date(epochSegundos * 1000).toLocaleDateString("pt-BR");
}

export function CasosLista() {
  const router = useRouter();
  const { data, error, loading, refetch } = useCasos();
  const [dialogAberto, setDialogAberto] = React.useState(false);

  function abrirCaso(id: string) {
    // `/casos/[id]` nasce em W3 (plano §1) — o cast é necessário porque
    // `typedRoutes` só conhece rotas com `page.tsx` já presente na árvore.
    router.push(`/casos/${id}` as Route);
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between gap-3">
        <p className="text-[0.9375rem] text-muted-foreground">
          Um caso reúne tudo sobre uma investigação: os alvos, as pesquisas, as evidências e o
          dossiê final.
        </p>
        <Button type="button" onClick={() => setDialogAberto(true)}>
          Novo caso
        </Button>
      </div>

      {loading ? (
        <TableSkeleton rows={6} cols={5} />
      ) : error ? (
        <ErrorState
          title="Falha ao listar casos"
          message={error.message}
          onRetry={() => refetch()}
        />
      ) : !data || data.length === 0 ? (
        <EmptyState
          title="Nenhum caso ainda"
          description="Um caso reúne tudo sobre uma investigação — os alvos, as pesquisas, as evidências e o dossiê final. Crie o primeiro para começar."
          actionLabel="Novo caso"
          onAction={() => setDialogAberto(true)}
        />
      ) : (
        <Table>
          <caption className="sr-only">Casos ({data.length})</caption>
          <THead>
            <TR className="hover:bg-card">
              <TH>Título</TH>
              <TH>Tipo</TH>
              <TH>Municípios</TH>
              <TH>Alvos</TH>
              <TH className="text-right">Criado em</TH>
            </TR>
          </THead>
          <TBody>
            {data.map((caso) => (
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
                <TD className="font-mono tabular-nums">
                  {alvoResumo(caso) || <span className="text-muted-foreground">—</span>}
                </TD>
                <TD className="text-right font-mono tabular-nums">
                  {formatarData(caso.criado_em)}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
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
