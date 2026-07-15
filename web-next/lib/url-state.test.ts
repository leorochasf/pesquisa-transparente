import { describe, expect, it } from "vitest";
import { readSearchParams, writeSearchParams } from "./url-state";

describe("readSearchParams", () => {
  it("lê município, seção e filtros da query string", () => {
    const sp = new URLSearchParams(
      "m=senadorcanedo&s=licitacoes&f%5Bano%5D=2024&f%5Bcnpj%5D=123",
    );
    const state = readSearchParams(sp);
    expect(state.municipio).toBe("senadorcanedo");
    expect(state.secao).toBe("licitacoes");
    expect(state.filtros).toEqual({ ano: 2024, cnpj: "123" });
  });

  it("retorna filtros undefined quando não há nenhum filtro na query", () => {
    const sp = new URLSearchParams("m=goiania");
    const state = readSearchParams(sp);
    expect(state.filtros).toBeUndefined();
  });

  it("ignora valor de ano não numérico", () => {
    const sp = new URLSearchParams("f%5Bano%5D=abc");
    const state = readSearchParams(sp);
    expect(state.filtros).toBeUndefined();
  });
});

describe("writeSearchParams", () => {
  it("serializa o estado de volta para query string", () => {
    const sp = writeSearchParams({
      municipio: "senadorcanedo",
      secao: "licitacoes",
      filtros: { ano: 2024 },
    });
    expect(sp.get("m")).toBe("senadorcanedo");
    expect(sp.get("s")).toBe("licitacoes");
    expect(sp.get("f[ano]")).toBe("2024");
  });

  it("omite chaves ausentes", () => {
    const sp = writeSearchParams({ municipio: "goiania" });
    expect(sp.has("s")).toBe(false);
    expect(sp.has("f[ano]")).toBe(false);
  });

  it("é a inversa de readSearchParams para um estado completo", () => {
    const original = new URLSearchParams(
      "m=senadorcanedo&s=licitacoes&f%5Bano%5D=2024&f%5Bcnpj%5D=00.000.000%2F0000-00",
    );
    const state = readSearchParams(original);
    const roundtrip = writeSearchParams(state);
    expect(readSearchParams(roundtrip)).toEqual(state);
  });
});
