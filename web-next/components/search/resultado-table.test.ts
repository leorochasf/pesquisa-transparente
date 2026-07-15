import { describe, expect, it } from "vitest";
import { toCsv } from "./resultado-table";
import type { ItemTransparencia } from "@/lib/api-types";

describe("toCsv", () => {
  it("não grava [object Object] quando uma coluna traz um objeto (ex.: raw)", () => {
    const items: ItemTransparencia[] = [
      { titulo: "Contrato X", raw: { foo: "bar" } },
    ];
    const csv = toCsv(items, ["titulo", "raw"]);

    expect(csv).not.toContain("[object Object]");
    expect(csv.split("\n")).toEqual(["titulo,raw", "Contrato X,"]);
  });
});
