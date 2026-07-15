import { describe, expect, it } from "vitest";
import { agruparItens } from "./dossie-itens";
import type { ItemCaso } from "@/lib/casos-types";

function item(overrides: Partial<ItemCaso>): ItemCaso {
  return {
    id: "it_1",
    caso_id: "caso_1",
    municipio: "trindade",
    secao: "dispensas",
    titulo: null,
    documento: null,
    valor: null,
    data: null,
    ref_registro: null,
    raw: {},
    origem: null,
    criado_em: 0,
    ...overrides,
  };
}

describe("agruparItens — residual rerun duplica itens (plano §7)", () => {
  it("agrupa por município+seção e por ref_registro.id dentro do grupo", () => {
    const itens: ItemCaso[] = [
      item({ id: "a", municipio: "trindade", secao: "dispensas", ref_registro: { id: "r1" } }),
      item({ id: "b", municipio: "trindade", secao: "dispensas", ref_registro: { id: "r1" } }),
      item({ id: "c", municipio: "trindade", secao: "dispensas", ref_registro: { id: "r2" } }),
      item({ id: "d", municipio: "itumbiara", secao: "contratos", ref_registro: { id: "r1" } }),
    ];
    const grupos = agruparItens(itens);
    expect(grupos).toHaveLength(2);

    const trindadeDispensas = grupos.find((g) => g.municipio === "trindade" && g.secao === "dispensas");
    expect(trindadeDispensas?.subgrupos).toHaveLength(2);
    expect(trindadeDispensas?.subgrupos.find((s) => s.refId === "r1")?.itens).toHaveLength(2);
    expect(trindadeDispensas?.subgrupos.find((s) => s.refId === "r2")?.itens).toHaveLength(1);
  });

  it("itens sem ref_registro.id caem no subgrupo refId=null — nunca deduplica", () => {
    const itens: ItemCaso[] = [
      item({ id: "a", ref_registro: null }),
      item({ id: "b", ref_registro: {} }),
      item({ id: "c", ref_registro: { numero: "123" } }),
    ];
    const grupos = agruparItens(itens);
    expect(grupos).toHaveLength(1);
    const semId = grupos[0].subgrupos.find((s) => s.refId === null);
    expect(semId?.itens.map((i) => i.id)).toEqual(["a", "b", "c"]);
  });
});
