import { describe, expect, it } from "vitest";
import { formatarCustoUsd, jobTipo, progressoTexto, resumirHomonimos, resumoTexto } from "./job-resumo";
import type { Job } from "./casos-types";

function job(overrides: Partial<Job>): Job {
  return {
    id: "job_1",
    caso_id: "caso_1",
    parametros: {},
    resultado_resumo: null,
    status: "rodando",
    progresso: null,
    iniciada_em: null,
    concluida_em: null,
    ...overrides,
  };
}

describe("jobTipo", () => {
  it("discrimina pelo parametros.tipo; ausente = pesquisa", () => {
    expect(jobTipo(job({ parametros: {} }))).toBe("pesquisa");
    expect(jobTipo(job({ parametros: { tipo: "folha" } }))).toBe("folha");
    expect(jobTipo(job({ parametros: { tipo: "investigacao" } }))).toBe("investigacao");
  });
});

describe("progressoTexto", () => {
  it("pesquisa: varrendo município X de Y", () => {
    const j = job({
      progresso: { municipio_atual: "trindade", municipios_feitos: 2, municipios_total: 6 },
    });
    expect(progressoTexto(j)).toBe("Varrendo trindade… 2 de 6 municípios.");
  });

  it("folha: coletando competência X de Y", () => {
    const j = job({
      parametros: { tipo: "folha" },
      progresso: { competencia_atual: "03/2025", feitas: 1, total: 3 },
    });
    expect(progressoTexto(j)).toBe("Coletando a folha de 03/2025… 1 de 3 competências.");
  });

  it("investigação: planejando", () => {
    const j = job({
      parametros: { tipo: "investigacao" },
      progresso: { etapa: "planejando" },
    });
    expect(progressoTexto(j)).toBe("O assistente está planejando a investigação…");
  });

  it("null sem progresso ainda (job na fila)", () => {
    expect(progressoTexto(job({ progresso: null }))).toBeNull();
  });
});

describe("resumoTexto — W0-F2: em status erro, só `erro` é garantido", () => {
  it("status erro só com {erro} não quebra e não inventa campos de sucesso", () => {
    const j = job({ status: "erro", resultado_resumo: { erro: "falha geral" } });
    const r = resumoTexto(j);
    expect(r).toEqual({ texto: "falha geral", tom: "destructive" });
  });

  it("status erro sem nenhum campo (resultado_resumo vazio) usa mensagem padrão", () => {
    const j = job({ status: "erro", resultado_resumo: {} });
    const r = resumoTexto(j);
    expect(r?.tom).toBe("destructive");
    expect(r?.texto).toBe("Falhou sem detalhe de erro informado pelo serviço.");
  });

  it("erro de folha (EvidenciaAmbigua) sem `avisos`/`itens` não lança undefined.length", () => {
    const j = job({
      parametros: { tipo: "folha" },
      status: "erro",
      resultado_resumo: { erro: "homônimos: JOANA (mat 1), JOANA (mat 2)", competencia: "03/2025" },
    });
    expect(() => resumoTexto(j)).not.toThrow();
  });

  it("ACEIT-F1: erro de folha com `competencia` (EvidenciaAmbigua) não repete a lista crua de candidatos — só aponta pro painel de homônimo", () => {
    const j = job({
      parametros: { tipo: "folha" },
      status: "erro",
      resultado_resumo: {
        erro: "'MARIA' casa com 470 servidores distintos em 01/2025 no portal de Senador Canedo — informe 'matricula' para desambiguar. Candidatos encontrados: A (matricula 1); B (matricula 2).",
        competencia: "01/2025",
      },
    });
    const r = resumoTexto(j);
    expect(r?.texto).not.toContain("Candidatos encontrados");
    expect(r?.texto).toContain("01/2025");
    expect(r?.tom).toBe("warning");
  });

  it("erro de folha SEM `competencia` (erro geral, não EvidenciaAmbigua) mostra o `erro` cru normalmente", () => {
    const j = job({
      parametros: { tipo: "folha" },
      status: "erro",
      resultado_resumo: { erro: "falha ao coletar a folha" },
    });
    expect(resumoTexto(j)).toEqual({ texto: "falha ao coletar a folha", tom: "destructive" });
  });

  it("interrompida mapeia para o texto fixo, ignorando resultado_resumo", () => {
    const j = job({ status: "interrompida", resultado_resumo: null });
    expect(resumoTexto(j)).toEqual({
      texto: "Interrompida (o serviço reiniciou) — refaça a ação.",
      tom: "warning",
    });
  });

  it("concluída de pesquisa sem `avisos` não inclui extras", () => {
    const j = job({ status: "concluida", resultado_resumo: { total_itens: 12 } });
    expect(resumoTexto(j)).toEqual({ texto: "12 registros encontrados.", tom: "success", extras: undefined });
  });

  it("concluída de investigação com teto_atingido vira warning + aviso honesto", () => {
    const j = job({
      parametros: { tipo: "investigacao" },
      status: "concluida",
      resultado_resumo: { subtarefas_ok: 4, lacunas: ["x"], custo_usd: 0.42, teto_atingido: true },
    });
    const r = resumoTexto(j);
    expect(r?.tom).toBe("warning");
    expect(r?.texto).toBe("4 etapas · 1 lacunas · custo US$ 0,42.");
    expect(r?.extras).toEqual([
      "Entrega parcial: o teto de custo/tempo foi atingido; veja as lacunas.",
    ]);
  });

  it("job ainda em fila/rodando não tem resumo (null)", () => {
    expect(resumoTexto(job({ status: "fila" }))).toBeNull();
    expect(resumoTexto(job({ status: "rodando" }))).toBeNull();
  });
});

describe("formatarCustoUsd — ACEIT-F3: pt-BR, sem esmagar centavos de dólar", () => {
  it("não esmaga custo pequeno para 'US$ 0.00' (soaria grátis)", () => {
    const texto = formatarCustoUsd(0.0113344);
    expect(texto).toBe("US$ 0,0113");
    expect(texto).not.toContain("0,00");
  });

  it("usa vírgula (pt-BR), não ponto (en-US)", () => {
    expect(formatarCustoUsd(0.42)).toBe("US$ 0,42");
    expect(formatarCustoUsd(0.42)).not.toContain(".");
  });
});

describe("resumirHomonimos — ACEIT-F1: trunca a lista de candidatos legivelmente", () => {
  it("com poucos candidatos, mostra todos e não sobra resto", () => {
    const erro =
      "'JOANA' casa com 2 servidores distintos em 03/2025 no portal de Senador Canedo — informe 'matricula' para desambiguar. Candidatos encontrados: JOANA A (matricula 1); JOANA B (matricula 2).";
    const r = resumirHomonimos(erro);
    expect(r.candidatosVisiveis).toEqual(["JOANA A (matricula 1)", "JOANA B (matricula 2)"]);
    expect(r.restantes).toBe(0);
    expect(r.prefixo).toContain("2 servidores distintos");
  });

  it("com 470 candidatos, trunca em 10 e reporta o restante — nunca esconde que há homônimos", () => {
    const candidatos = Array.from({ length: 470 }, (_, i) => `NOME ${i} (matricula ${i})`).join("; ");
    const erro = `'MARIA' casa com 470 servidores distintos em 01/2025 no portal de Senador Canedo — informe 'matricula' para desambiguar. Candidatos encontrados: ${candidatos}.`;
    const r = resumirHomonimos(erro);
    expect(r.candidatosVisiveis).toHaveLength(10);
    expect(r.candidatosVisiveis[0]).toBe("NOME 0 (matricula 0)");
    expect(r.restantes).toBe(460);
    expect(r.textoCompleto).toBe(erro);
  });

  it("sem o marcador 'Candidatos encontrados' (mensagem de erro genérica), devolve o texto inteiro como prefixo", () => {
    const r = resumirHomonimos("falha ao coletar a folha");
    expect(r.prefixo).toBe("falha ao coletar a folha");
    expect(r.candidatosVisiveis).toEqual([]);
    expect(r.restantes).toBe(0);
  });
});
