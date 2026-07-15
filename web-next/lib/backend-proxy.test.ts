import { afterEach, describe, expect, it, vi } from "vitest";
import { proxyBackend, proxyBackendBinary, proxyBackendPost } from "./backend-proxy";

describe("proxyBackend", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("retorna 502 com mensagem amigável em pt-BR quando o backend está inacessível", async () => {
    vi.spyOn(global, "fetch").mockRejectedValue(new Error("ECONNREFUSED"));

    const res = await proxyBackend("/api/municipios");

    expect(res.status).toBe(502);
    const body = await res.json();
    expect(body.error).toMatch(/não foi possível conectar ao serviço de busca/i);
  });

  it("repassa status e corpo de sucesso do backend sem alteração", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ items: [] }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );

    const res = await proxyBackend("/api/buscar/senadorcanedo/licitacoes");

    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ items: [] });
  });

  it("retorna 504 com mensagem amigável em pt-BR quando a requisição estoura o timeout (B3)", async () => {
    const timeoutError = new DOMException("The operation was aborted due to timeout", "TimeoutError");
    vi.spyOn(global, "fetch").mockRejectedValue(timeoutError);

    const res = await proxyBackend("/api/buscar/rioverde/licitacoes");

    expect(res.status).toBe(504);
    const body = await res.json();
    expect(body.error).toMatch(/demorou demais/i);
  });

  it("repassa status e corpo de erro estruturado do backend (contrato {error})", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ error: "Falha ao acessar o portal." }), {
        status: 502,
        headers: { "content-type": "application/json" },
      }),
    );

    const res = await proxyBackend("/api/buscar/goiania/licitacoes");

    expect(res.status).toBe(502);
    expect(await res.json()).toEqual({ error: "Falha ao acessar o portal." });
  });
});

describe("proxyBackendBinary", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("repassa application/pdf como buffer preservando content-disposition (comportamento antigo)", async () => {
    const bytes = new Uint8Array([0x25, 0x50, 0x44, 0x46]); // "%PDF"
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(bytes, {
        status: 200,
        headers: {
          "content-type": "application/pdf",
          "content-disposition": 'inline; filename="anexo.pdf"',
        },
      }),
    );

    const res = await proxyBackendBinary("/api/anexos/goiania/contratos/download?ref=1");

    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toBe("application/pdf");
    expect(res.headers.get("content-disposition")).toBe('inline; filename="anexo.pdf"');
    const buf = new Uint8Array(await res.arrayBuffer());
    expect(Array.from(buf)).toEqual(Array.from(bytes));
  });

  it("W0-F1: repassa image/png como buffer preservando content-disposition (evidência de folha)", async () => {
    const bytes = new Uint8Array([0x89, 0x50, 0x4e, 0x47]); // assinatura PNG
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(bytes, {
        status: 200,
        headers: {
          "content-type": "image/png",
          "content-disposition": 'inline; filename="evidencia.png"',
        },
      }),
    );

    const res = await proxyBackendBinary("/api/casos/caso_x/evidencias/ev_1/arquivo");

    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toBe("image/png");
    expect(res.headers.get("content-disposition")).toBe('inline; filename="evidencia.png"');
    const buf = new Uint8Array(await res.arrayBuffer());
    expect(Array.from(buf)).toEqual(Array.from(bytes));
  });

  it("repassa erro JSON como texto (não tenta ler como binário)", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ error: "Evidência não encontrada." }), {
        status: 404,
        headers: { "content-type": "application/json" },
      }),
    );

    const res = await proxyBackendBinary("/api/casos/caso_x/evidencias/ev_9/arquivo");

    expect(res.status).toBe(404);
    expect(await res.json()).toEqual({ error: "Evidência não encontrada." });
  });
});

describe("proxyBackendPost", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("envia o corpo como JSON e repassa a resposta de sucesso", async () => {
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ job_id: "job_1" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );

    const res = await proxyBackendPost("/api/casos/caso_x/pesquisar", { q: "termo" });

    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ job_id: "job_1" });
    const [, init] = fetchSpy.mock.calls[0];
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(JSON.stringify({ q: "termo" }));
  });

  it("retorna 502 com mensagem amigável quando o backend está inacessível", async () => {
    vi.spyOn(global, "fetch").mockRejectedValue(new Error("ECONNREFUSED"));

    const res = await proxyBackendPost("/api/casos/caso_x/pesquisar", {});

    expect(res.status).toBe(502);
    const body = await res.json();
    expect(body.error).toMatch(/não foi possível conectar ao serviço de busca/i);
  });
});
