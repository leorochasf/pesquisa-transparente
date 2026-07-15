import { afterEach, beforeAll, describe, expect, it } from "vitest";
import {
  gravarJobAtivo,
  lerJobAtivo,
  limparJobAtivo,
  statusBadgeVariant,
  statusTexto,
} from "./use-job";
import type { JobStatus } from "@/lib/casos-types";

// Ambiente de teste é "node" (vitest.config.ts) — sem `window`/localStorage
// nativos. Os helpers de slot de job ativo só tocam `window.localStorage`
// (guardados por `typeof window === "undefined"`); um stub mínimo em memória
// basta, sem precisar de jsdom (não é dependência do projeto).
beforeAll(() => {
  const mem = new Map<string, string>();
  (globalThis as { window?: unknown }).window = {
    localStorage: {
      getItem: (k: string) => mem.get(k) ?? null,
      setItem: (k: string, v: string) => {
        mem.set(k, v);
      },
      removeItem: (k: string) => {
        mem.delete(k);
      },
    },
  };
});

describe("statusTexto (plano §4.2 — mapa status→texto pt-BR)", () => {
  it("nunca expõe o status cru — sempre um texto de jurista", () => {
    const casos: Record<JobStatus, string> = {
      fila: "Na fila…",
      rodando: "Em andamento…",
      concluida: "Concluída",
      erro: "Falhou",
      interrompida: "Interrompida (o serviço reiniciou) — refaça a ação",
    };
    for (const [status, texto] of Object.entries(casos)) {
      expect(statusTexto(status as JobStatus)).toBe(texto);
    }
  });
});

describe("statusBadgeVariant", () => {
  it("mapeia cada status a uma variante de cor distinta (plano §4.2)", () => {
    expect(statusBadgeVariant("fila")).toBe("secondary");
    expect(statusBadgeVariant("rodando")).toBe("info");
    expect(statusBadgeVariant("concluida")).toBe("success");
    expect(statusBadgeVariant("erro")).toBe("destructive");
    expect(statusBadgeVariant("interrompida")).toBe("warning");
  });
});

describe("slot de job ativo (localStorage, plano §4.3)", () => {
  afterEach(() => {
    limparJobAtivo("caso_x");
  });

  it("grava, lê e limpa o slot bt:caso:<id>:jobAtivo", () => {
    expect(lerJobAtivo("caso_x")).toBeNull();

    gravarJobAtivo("caso_x", "job_1", "pesquisa");
    expect(lerJobAtivo("caso_x")).toEqual({ job_id: "job_1", tipo: "pesquisa" });

    limparJobAtivo("caso_x");
    expect(lerJobAtivo("caso_x")).toBeNull();
  });

  it("não quebra com JSON corrompido no slot — trata como ausente", () => {
    window.localStorage.setItem("bt:caso:caso_x:jobAtivo", "{corrompido");
    expect(lerJobAtivo("caso_x")).toBeNull();
  });
});
