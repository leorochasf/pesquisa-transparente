import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import type { GrupoEntidade, ItemEntidade } from "@/lib/api-types";
import { DocumentosButton } from "./documentos-button";

const SECAO_LABEL: Record<string, string> = {
  contratos: "Contratos",
  licitacoes: "Licitações",
  dispensas: "Dispensas",
};

function cell(v: string | undefined): React.ReactNode {
  if (!v) return <span className="text-muted-foreground">—</span>;
  return v;
}

export function GrupoResultados({ slug, grupo }: { slug: string; grupo: GrupoEntidade }) {
  const itens = grupo.itens as ItemEntidade[];
  const secaoAnexo = grupo.secao as "contratos" | "licitacoes" | "dispensas";
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-2">
        <CardTitle>{SECAO_LABEL[grupo.secao] ?? grupo.secao}</CardTitle>
        <Badge variant="secondary">
          {grupo.total} {grupo.total === 1 ? "resultado" : "resultados"}
        </Badge>
      </CardHeader>
      <CardContent>
        {grupo.truncado && (
          <p className="mb-3 text-xs text-muted-foreground">
            Mostrando os primeiros {grupo.total} de {grupo.total_portal} registros do portal
            (varredura limitada).
          </p>
        )}
        {itens.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nenhum item encontrado nesta seção.</p>
        ) : (
          <Table>
            <caption className="sr-only">
              {SECAO_LABEL[grupo.secao] ?? grupo.secao} encontrados ({itens.length})
            </caption>
            <THead>
              <TR className="hover:bg-card">
                <TH stickyLeft>Título</TH>
                <TH>Fornecedor</TH>
                <TH className="text-right">Documento</TH>
                <TH className="text-right">Valor</TH>
                <TH className="text-right">Data</TH>
                {grupo.secao === "contratos" && <TH>Aditivo</TH>}
                <TH>Documentos</TH>
              </TR>
            </THead>
            <TBody>
              {itens.map((it, i) => (
                <TR key={i}>
                  <TD stickyLeft>{cell(it.titulo)}</TD>
                  <TD>{cell(it.fornecedor)}</TD>
                  <TD className="font-mono tabular-nums text-right">{cell(it.documento)}</TD>
                  <TD className="font-mono tabular-nums text-right">{cell(it.valor)}</TD>
                  <TD className="font-mono tabular-nums text-right">{cell(it.data)}</TD>
                  {grupo.secao === "contratos" && (
                    <TD>
                      {it.tem_aditivo ? (
                        <Badge variant="warning">tem aditivo</Badge>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TD>
                  )}
                  <TD>
                    {it.ref_registro?.id ? (
                      <DocumentosButton slug={slug} secao={secaoAnexo} refRegistro={it.ref_registro} />
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
