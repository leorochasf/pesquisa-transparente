import { describe, expect, it } from "vitest";
import { cn } from "./utils";

describe("cn", () => {
  it("combina classes condicionais, descartando falsy", () => {
    expect(cn("a", false && "b", null, undefined, "c")).toBe("a c");
  });

  it("resolve conflitos de utilitários Tailwind mantendo o último", () => {
    expect(cn("px-2", "px-4")).toBe("px-4");
  });
});
