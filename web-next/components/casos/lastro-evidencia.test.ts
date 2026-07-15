import { describe, expect, it } from "vitest";
import { shaCurto } from "./lastro-evidencia";

describe("shaCurto — formatação do lastro (ev_id/sha256, coluna-razão)", () => {
  it("corta o sha256 completo para 8 caracteres", () => {
    const sha = "a3f9c2d1e8b7065432109876543210fedcba9876543210fedcba9876543210";
    expect(shaCurto(sha)).toBe("a3f9c2d1");
    expect(shaCurto(sha)).toHaveLength(8);
  });

  it("não quebra em hash mais curto que 8 chars — retorna o que houver", () => {
    expect(shaCurto("ab12")).toBe("ab12");
  });
});
