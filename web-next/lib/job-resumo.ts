/** Mapeamento pt-BR de progresso e resultado de job por tipo (plano §4.1/§4.2).
 *  ⚠ W0-F2 — em `status === "erro"` o único campo garantido é `erro?: string`;
 *  todo acesso a campo de sucesso passa por checagem de presença. Separado de
 *  `components/casos/job-progresso.tsx` para ser testável sem DOM (ambiente
 *  de teste é `node`, plano/`vitest.config.ts`). */

import type {
  Job,
  ProgressoFolha,
  ProgressoInvestigacao,
  ProgressoPesquisa,
  ResultadoFolha,
  ResultadoInvestigacao,
  ResultadoPesquisa,
} from "./casos-types";

export type JobTipo = "pesquisa" | "folha" | "investigacao";

export function jobTipo(job: Job): JobTipo {
  const tipo = job.parametros?.tipo;
  if (tipo === "folha") return "folha";
  if (tipo === "investigacao") return "investigacao";
  return "pesquisa";
}

/** Texto de progresso legível enquanto o job está `fila`/`rodando` (plano §4.2). */
export function progressoTexto(job: Job): string | null {
  if (!job.progresso) return null;
  const tipo = jobTipo(job);

  if (tipo === "pesquisa") {
    const p = job.progresso as ProgressoPesquisa;
    const municipio = p.municipio_atual ?? "—";
    return `Varrendo ${municipio}… ${p.municipios_feitos} de ${p.municipios_total} municípios.`;
  }
  if (tipo === "folha") {
    const p = job.progresso as ProgressoFolha;
    const competencia = p.competencia_atual ?? "—";
    return `Coletando a folha de ${competencia}… ${p.feitas} de ${p.total} competências.`;
  }
  const p = job.progresso as ProgressoInvestigacao;
  if (p.etapa === "planejando") return "O assistente está planejando a investigação…";
  return `${p.subtarefas_ok ?? 0} etapas concluídas · ${p.lacunas ?? 0} lacunas.`;
}

// ACEIT-F3: `toFixed(2)` em en-US esmagava custos pequenos (US$ 0,0113 virava
// "US$ 0.01") e usava ponto decimal numa UI pt-BR. `maximumSignificantDigits`
// preserva a ordem de grandeza real do centavo de dólar sem exagerar casas em
// custos maiores (US$ 0,42 continua "US$ 0,42").
const FORMATADOR_CUSTO_USD = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "USD",
  maximumSignificantDigits: 3,
});

export function formatarCustoUsd(valor: number): string {
  // `Intl.NumberFormat` insere um espaço estreito sem quebra (U+00A0) entre o
  // símbolo e o valor — invisível, mas inconsistente com o resto do texto
  // pt-BR simples da UI (e frágil pra copiar/colar); normaliza pra espaço comum.
  return FORMATADOR_CUSTO_USD.format(valor).replace(/ /g, " ");
}

const MARCADOR_CANDIDATOS = "Candidatos encontrados: ";
const MAX_CANDIDATOS_VISIVEIS = 10;

export interface HomonimosResumo {
  /** Frase antes da lista de candidatos (sempre visível). */
  prefixo: string;
  /** Primeiros `MAX_CANDIDATOS_VISIVEIS` candidatos, um por linha. */
  candidatosVisiveis: string[];
  /** Quantos candidatos ficaram de fora da lista visível. */
  restantes: number;
  /** Mensagem original, íntegra — para o `<details>` de expandir. */
  textoCompleto: string;
}

/** ACEIT-F1: a mensagem de `EvidenciaAmbigua` (`busca_go/nucleo/evidencia.py::
 *  _candidatos_folha_str`) traz "<prefixo>. Candidatos encontrados: nome
 *  (matricula X); nome (matricula Y); ….", e com homônimos comuns (ex.:
 *  "MARIA") pode trazer centenas — despejada crua vira parede de texto
 *  ilegível. Trunca a lista visível mantendo a mensagem completa acessível
 *  (via `textoCompleto`, para um `<details>`) — nunca esconde que há
 *  homônimos nem decide sozinho por um deles. */
export function resumirHomonimos(erro: string, max = MAX_CANDIDATOS_VISIVEIS): HomonimosResumo {
  const idx = erro.indexOf(MARCADOR_CANDIDATOS);
  if (idx === -1) {
    return { prefixo: erro, candidatosVisiveis: [], restantes: 0, textoCompleto: erro };
  }
  const prefixo = erro.slice(0, idx).trim();
  const blob = erro.slice(idx + MARCADOR_CANDIDATOS.length).replace(/\.\s*$/, "");
  const candidatos = blob
    .split(";")
    .map((c) => c.trim())
    .filter(Boolean);
  const candidatosVisiveis = candidatos.slice(0, max);
  return {
    prefixo,
    candidatosVisiveis,
    restantes: Math.max(0, candidatos.length - candidatosVisiveis.length),
    textoCompleto: erro,
  };
}

export interface ResumoRender {
  texto: string;
  tom: "success" | "warning" | "destructive" | "info";
  extras?: string[];
}

/** Resumo legível ao terminar (status terminal). Defensivo por construção
 *  (W0-F2): em `erro`, só lê `resultado_resumo?.erro`; NUNCA assume
 *  `total_itens`/`avisos`/`lacunas`/`custo_usd` fora de `concluida`. */
export function resumoTexto(job: Job): ResumoRender | null {
  if (job.status === "fila" || job.status === "rodando") return null;

  if (job.status === "interrompida") {
    return {
      texto: "Interrompida (o serviço reiniciou) — refaça a ação.",
      tom: "warning",
    };
  }

  if (job.status === "erro") {
    const resumo = job.resultado_resumo as { erro?: string; competencia?: string } | null;
    // ACEIT-F1: `EvidenciaAmbigua` (folha, erro+competencia — mesma assinatura
    // usada por `dossie.tsx::evidenciaAmbiguaDe`) já aparece por extenso, com
    // os candidatos truncados legivelmente, no painel "Servidor ambíguo"
    // (`dossie-acoes.tsx`). Repetir a mensagem crua aqui (centenas de nomes)
    // dobra a parede de texto — só aponta para o painel acima.
    if (jobTipo(job) === "folha" && resumo?.erro && resumo?.competencia) {
      return {
        texto: `Servidor ambíguo em ${resumo.competencia} — veja "Servidor ambíguo" acima e informe a matrícula.`,
        tom: "warning",
      };
    }
    return { texto: resumo?.erro ?? "Falhou sem detalhe de erro informado pelo serviço.", tom: "destructive" };
  }

  const r = job.resultado_resumo;
  const tipo = jobTipo(job);
  if (!r) return { texto: "Concluída sem resumo disponível.", tom: "info" };

  if (tipo === "pesquisa") {
    const rp = r as ResultadoPesquisa;
    return {
      texto: `${rp.total_itens ?? 0} registros encontrados.`,
      tom: "success",
      extras: rp.avisos?.length ? rp.avisos : undefined,
    };
  }

  if (tipo === "folha") {
    const rf = r as ResultadoFolha;
    return {
      texto: `${rf.itens?.length ?? 0} competências coletadas com evidência.`,
      tom: "success",
      extras: rf.falhas?.length ? rf.falhas.map((f) => `${f.competencia}: ${f.erro}`) : undefined,
    };
  }

  const ri = r as ResultadoInvestigacao;
  const partes = [
    `${ri.subtarefas_ok ?? 0} etapas`,
    `${ri.lacunas?.length ?? 0} lacunas`,
  ];
  if (ri.custo_usd != null) partes.push(`custo ${formatarCustoUsd(ri.custo_usd)}`);
  return {
    texto: `${partes.join(" · ")}.`,
    tom: ri.teto_atingido ? "warning" : "success",
    extras: ri.teto_atingido
      ? ["Entrega parcial: o teto de custo/tempo foi atingido; veja as lacunas."]
      : undefined,
  };
}
