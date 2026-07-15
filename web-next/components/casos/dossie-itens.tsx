import type { ReactNode } from "react";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { EmptyState } from "@/components/shared/empty-state";
import { LastroEvidencia } from "@/components/casos/lastro-evidencia";
import { MUNICIPIOS_CASO } from "@/components/casos/caso-tipo";
import type { CasoDetalhe, EvidenciaCaso, ItemCaso } from "@/lib/casos-types";

const NOME_MUNICIPIO = new Map<string, string>(MUNICIPIOS_CASO.map((m) => [m.value, m.label]));
const SECAO_ROTULO: Record<string, string> = {
  contratos: "Contratos",
  dispensas: "Dispensas",
  licitacoes: "Licitações",
  despesas: "Despesas",
  folha: "Folha",
};

function rotuloMunicipio(slug: string): string {
  return NOME_MUNICIPIO.get(slug) ?? slug;
}

function rotuloSecao(secao: string): string {
  return SECAO_ROTULO[secao] ?? secao;
}

interface GrupoChave {
  municipio: string;
  secao: string;
}

interface Subgrupo {
  refId: string | null;
  itens: ItemCaso[];
}

interface Grupo extends GrupoChave {
  subgrupos: Subgrupo[];
}

/** Agrupa itens por município+seção e, dentro, por `ref_registro.id`
 *  (residual "rerun duplica itens" — plano §7). Itens sem id estável caem no
 *  subgrupo `refId: null` ("registros sem identificador estável"). Exportado
 *  puro para ser testável sem DOM. */
export function agruparItens(itens: ItemCaso[]): Grupo[] {
  const grupos = new Map<string, Grupo>();
  for (const item of itens) {
    const chave = `${item.municipio}::${item.secao}`;
    let grupo = grupos.get(chave);
    if (!grupo) {
      grupo = { municipio: item.municipio, secao: item.secao, subgrupos: [] };
      grupos.set(chave, grupo);
    }
    const refId = item.ref_registro?.id ?? null;
    let subgrupo = grupo.subgrupos.find((s) => s.refId === refId);
    if (!subgrupo) {
      subgrupo = { refId, itens: [] };
      grupo.subgrupos.push(subgrupo);
    }
    subgrupo.itens.push(item);
  }
  return Array.from(grupos.values());
}

function evidenciasDoItem(itemId: string, evidencias: EvidenciaCaso[]): EvidenciaCaso[] {
  return evidencias.filter((e) => e.item_id === itemId);
}

function celula(valor: string | null): ReactNode {
  return valor ? valor : <span className="text-muted-foreground">—</span>;
}

interface DossieItensProps {
  caso: CasoDetalhe;
}

/** Seção 4 do dossiê (plano §1.2): tabela dos itens com lastro por linha,
 *  agrupada por município/seção — resolve o residual "rerun duplica itens"
 *  sem nunca deduplicar (perderia lastro). Subgrupo de evidências do caso não
 *  vinculadas a item (W0-F3, §1.2). */
export function DossieItens({ caso }: DossieItensProps) {
  if (caso.itens.length === 0) {
    return (
      <section aria-labelledby="dossie-itens-titulo">
        <h2 id="dossie-itens-titulo" className="text-[1.0625rem] font-semibold leading-[1.35]">
          Itens do dossiê
        </h2>
        <div className="mt-3">
          <EmptyState
            title="Nenhum registro ainda"
            description="Use “Investigar” para o assistente varrer, ou “Pesquisar registros” / “Coletar folha” para buscar você mesmo."
          />
        </div>
      </section>
    );
  }

  const grupos = agruparItens(caso.itens);
  const evidenciasDoCaso = caso.evidencias.filter((e) => !e.item_id);

  return (
    <section aria-labelledby="dossie-itens-titulo">
      <h2 id="dossie-itens-titulo" className="text-[1.0625rem] font-semibold leading-[1.35]">
        Itens do dossiê
      </h2>

      <div className="mt-3 space-y-6">
        {grupos.map((grupo) => (
          <div key={`${grupo.municipio}::${grupo.secao}`}>
            <h3 className="mb-2 text-[0.9375rem] font-semibold">
              {rotuloMunicipio(grupo.municipio)} · {rotuloSecao(grupo.secao)}
            </h3>
            {grupo.subgrupos.map((sub) => (
              <div key={sub.refId ?? "sem-id-estavel"} className="mb-3">
                {sub.refId === null && (
                  <p className="mb-1 text-[0.8125rem] text-muted-foreground">
                    Registros sem identificador estável (podem repetir entre varreduras) ·{" "}
                    {sub.itens.length}
                  </p>
                )}
                <Table>
                  <caption className="sr-only">
                    Itens de {rotuloMunicipio(grupo.municipio)} — {rotuloSecao(grupo.secao)}
                  </caption>
                  <THead>
                    <TR className="hover:bg-card">
                      <TH>Título / documento</TH>
                      <TH className="text-right">Valor</TH>
                      <TH className="text-right">Data</TH>
                      <TH>Lastro</TH>
                    </TR>
                  </THead>
                  <TBody>
                    {sub.itens.map((item) => (
                      <TR key={item.id}>
                        <TD>
                          <p>{celula(item.titulo)}</p>
                          {item.documento && (
                            <p className="text-[0.8125rem] text-muted-foreground">
                              {item.documento}
                            </p>
                          )}
                        </TD>
                        <TD className="text-right font-mono tabular-nums">{celula(item.valor)}</TD>
                        <TD className="text-right font-mono tabular-nums">{celula(item.data)}</TD>
                        <TD>
                          <LastroEvidencia
                            casoId={caso.id}
                            evidencias={evidenciasDoItem(item.id, caso.evidencias)}
                          />
                        </TD>
                      </TR>
                    ))}
                  </TBody>
                </Table>
              </div>
            ))}
          </div>
        ))}
      </div>

      {evidenciasDoCaso.length > 0 && (
        <div className="mt-6">
          <h3 className="mb-2 text-[0.9375rem] font-semibold">
            Evidências do caso (não vinculadas a um registro)
          </h3>
          <LastroEvidencia casoId={caso.id} evidencias={evidenciasDoCaso} />
        </div>
      )}
    </section>
  );
}
