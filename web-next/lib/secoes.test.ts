import { describe, expect, it } from "vitest";
import { composeSecaoOptions } from "./secoes";

describe("composeSecaoOptions", () => {
  it("retorna a lista descoberta quando a secao ativa ja esta nela", () => {
    expect(composeSecaoOptions(["atas", "contratos"], "atas")).toEqual([
      "atas",
      "contratos",
    ]);
  });

  it("inclui a secao ativa mesmo se a descoberta ao vivo nao a retornou (BUG-16)", () => {
    expect(
      composeSecaoOptions(["atas", "contratos"], "legislacao"),
    ).toEqual(["atas", "contratos", "legislacao"]);
  });

  it("mantem ordem alfabetica ao injetar a secao ativa", () => {
    expect(composeSecaoOptions(["contratos", "sancoes"], "atas")).toEqual([
      "atas",
      "contratos",
      "sancoes",
    ]);
  });

  it("funciona com descoberta ainda nula (loading) e secao ativa vinda da URL", () => {
    expect(composeSecaoOptions(null, "legislacao")).toEqual(["legislacao"]);
  });

  it("retorna lista vazia sem secao ativa e sem descoberta", () => {
    expect(composeSecaoOptions(null, "")).toEqual([]);
  });

  it("nao duplica quando secao ativa vazia", () => {
    expect(composeSecaoOptions(["atas"], "")).toEqual(["atas"]);
  });
});
