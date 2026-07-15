import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import type { GrupoEntidade, ServidorFolha } from "@/lib/api-types";

function cell(v: string | undefined): React.ReactNode {
  if (!v) return <span className="text-muted-foreground">—</span>;
  return v;
}

function ServidorCard({ servidor }: { servidor: ServidorFolha }) {
  return (
    <Card>
      <CardHeader className="gap-1 pb-3">
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle>{servidor.nome || "Nome não informado"}</CardTitle>
          <Badge variant="outline">
            matrícula: {servidor.matricula || "não informada"}
          </Badge>
        </div>
        <p className="text-xs text-muted-foreground">
          {[servidor.cargo, servidor.lotacao, servidor.orgao].filter(Boolean).join(" · ") ||
            "Cargo/lotação não informados"}
        </p>
      </CardHeader>
      <CardContent className="pt-0">
        <Table>
          <caption className="sr-only">
            Folhas de {servidor.nome} ({servidor.folhas.length})
          </caption>
          <THead>
            <TR className="hover:bg-card">
              <TH>Ano</TH>
              <TH>Mês</TH>
              <TH>Tipo</TH>
              <TH className="text-right">Proventos</TH>
              <TH className="text-right">Descontos</TH>
              <TH className="text-right">Líquido</TH>
            </TR>
          </THead>
          <TBody>
            {servidor.folhas.map((f, i) => (
              <TR key={i}>
                <TD>{cell(f.ano)}</TD>
                <TD>{cell(f.mes)}</TD>
                <TD>{cell(f.tipo_folha)}</TD>
                <TD className="font-mono tabular-nums text-right">{cell(f.proventos)}</TD>
                <TD className="font-mono tabular-nums text-right">{cell(f.descontos)}</TD>
                <TD className="font-mono tabular-nums text-right">{cell(f.liquido)}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </CardContent>
    </Card>
  );
}

export function GrupoFolha({ grupo }: { grupo: GrupoEntidade }) {
  const servidores = grupo.servidores ?? [];
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-2">
        <CardTitle>Folha de pagamento</CardTitle>
        <Badge variant="secondary">
          {servidores.length} {servidores.length === 1 ? "servidor" : "servidores"}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-4">
        {grupo.truncado && (
          <p className="text-xs text-muted-foreground">
            Mostrando os primeiros {grupo.total} de {grupo.total_portal} registros do portal
            (varredura limitada).
          </p>
        )}
        {servidores.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nenhum servidor encontrado neste período.</p>
        ) : (
          servidores.map((s, i) => (
            <ServidorCard key={s.matricula || `nome-${i}`} servidor={s} />
          ))
        )}
      </CardContent>
    </Card>
  );
}
