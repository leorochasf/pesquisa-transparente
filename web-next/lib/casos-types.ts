/** Tipos do modo Caso/Dossiê. Contrato congelado em
 *  AUDITORIA/frontend-caso/01-plano-ux.md §2 — cada campo cita a origem Python
 *  (busca_go/nucleo/casos.py, busca_go/api.py). Chaves exatas dos dicts de
 *  retorno reais, não dos response_model (genéricos, dict[str, Any]). */

// origem: busca_go/nucleo/casos.py::listar_casos (linhas 76–87) — SEM itens/ev/anotações
export interface CasoResumo {
  id: string; // casos.py:78 ("caso_<slug>_<yyyymmdd>_<hex6>")
  titulo: string; // casos.py:79
  tipo: string; // casos.py:80 ("dispensa_advocacia"|"dano_erario_folha"|"livre" p/ a UI)
  alvos: CasoAlvos; // casos.py:81 (json de alvos_json)
  municipios: string[]; // casos.py:82 (slugs dos 6 municípios)
  criado_em: number; // casos.py:83 (epoch segundos, float)
  atualizado_em: number; // casos.py:84
}

// alvos_json é livre no banco; a UI usa este subconjunto (api.py::_extrair_q:435-436)
export interface CasoAlvos {
  nome?: string;
  cnpj?: string;
  servidor?: string;
  [k: string]: unknown;
}

// origem: busca_go/nucleo/casos.py::obter_caso (linhas 105–116)
export interface CasoDetalhe extends CasoResumo {
  itens: ItemCaso[]; // casos.py:113
  evidencias: EvidenciaCaso[]; // casos.py:114
  anotacoes: AnotacaoCaso[]; // casos.py:115
}

// origem: busca_go/nucleo/casos.py::_item_row_to_dict (linhas 128–142)
export interface ItemCaso {
  id: string; // casos.py:130 ("it_<sha>")
  caso_id: string; // casos.py:131
  municipio: string; // casos.py:132
  secao: string; // casos.py:133 (contratos|dispensas|licitacoes|despesas|folha)
  titulo: string | null; // casos.py:134
  documento: string | null; // casos.py:135
  valor: string | null; // casos.py:136
  data: string | null; // casos.py:137
  ref_registro: RefRegistroCaso | null; // casos.py:138
  raw: Record<string, unknown>; // casos.py:139
  origem: string[] | null; // casos.py:140 (["cnpj","nome"] dedup)
  criado_em: number; // casos.py:141
}

export interface RefRegistroCaso {
  id?: string;
  numero?: string;
  ano?: string;
  [k: string]: unknown;
}

// origem: busca_go/nucleo/casos.py::_evidencia_row_to_dict (linhas 242–254)
export interface EvidenciaCaso {
  id: string; // casos.py:244 ("ev_...")
  caso_id: string; // casos.py:245
  item_id: string | null; // casos.py:246 (null = evidência do caso)
  tipo: "pdf" | "screenshot" | "json"; // casos.py:247
  caminho_local: string; // casos.py:248
  url_origem: string; // casos.py:249
  sha256: string; // casos.py:250 (hash completo; UI exibe curto — 8 chars)
  bytes: number | null; // casos.py:251
  content_type: string | null; // casos.py:252 ("application/pdf" | "image/png" | ...)
  coletado_em: number; // casos.py:253
}

// origem: busca_go/nucleo/casos.py::_anotacao_row_to_dict (linhas 260–268)
export interface AnotacaoCaso {
  id: string; // casos.py:262
  caso_id: string; // casos.py:263
  item_id: string | null; // casos.py:264 (null = anotação do caso)
  tag: string | null; // casos.py:265
  texto: string; // casos.py:266
  criado_em: number; // casos.py:267
}

// origem: busca_go/api.py::CasoIn (linhas 381–385) → POST /api/casos
export interface CriarCasoBody {
  titulo: string;
  tipo: string;
  alvos?: CasoAlvos; // default {} (api.py:384)
  municipios: string[]; // >=1 obrigatório (api.py:500-502)
}
// resposta: CasoDetalhe (api.py::criar_caso:498-503)

// origem: busca_go/api.py::PesquisarCasoIn (linhas 400–404) → POST /api/casos/{id}/pesquisar
export interface PesquisarCasoBody {
  q?: string; // opcional: se ausente, backend usa alvos (api.py:524)
  municipios?: string[]; // opcional: default = municípios do caso (api.py:530)
  ano?: number;
  mes?: number;
}
// resposta: { job_id: string } (api.py:516,539)

// origem: busca_go/api.py::FolhaCasoIn + CompetenciaIn (linhas 407–416) → POST /api/casos/{id}/folha
export interface FolhaCasoBody {
  municipio: string; // um dos 6 (api.py:622)
  servidor: string; // nome OU matrícula, não-vazio (api.py:623-624)
  matricula?: string; // desambigua homônimo (api.py:415)
  competencias: Competencia[]; // >=1 (api.py:625-626); mes 1..12 (api.py:627-629)
}
export interface Competencia {
  ano: number;
  mes: number;
} // api.py:407-409
// resposta: { job_id: string } (api.py:614,646)

// origem: busca_go/api.py::InvestigarCasoIn (linhas 710–711) → POST /api/casos/{id}/investigar
export interface InvestigarCasoBody {
  descricao?: string; // opcional: default = descrição derivada do caso (api.py:777)
}
// resposta: { job_id: string } (api.py:768,780)
// PRÉ-CONDIÇÃO: sem OPENROUTER_API_KEY o backend responde 400 (api.py:774-775)

// origem: busca_go/api.py::AnotacaoIn (linhas 394–398) → POST /api/casos/{id}/anotacoes
export interface AnotacaoBody {
  item_id?: string;
  tag?: string;
  texto: string;
}
// resposta: AnotacaoCaso (api.py:657-662)

// ENVELOPE — origem: busca_go/nucleo/casos.py::obter_busca (linhas 342–357) = GET /api/jobs/{job_id}
export type JobStatus = "fila" | "rodando" | "concluida" | "erro" | "interrompida";
// valores: casos.py:310 ('fila'), api.py ('rodando'/'concluida'/'erro'),
//          casos.py:23 STATUS_TERMINAIS={concluida,erro,interrompida}, casos.py:369 ('interrompida')

export interface Job<P = JobProgresso, R = JobResultado> {
  id: string; // casos.py:349
  caso_id: string; // casos.py:350
  parametros: JobParametros; // casos.py:351
  resultado_resumo: R | null; // casos.py:352 (null enquanto não terminou)
  status: JobStatus; // casos.py:353
  progresso: P | null; // casos.py:354 (null enquanto na fila)
  iniciada_em: number | null; // casos.py:355
  concluida_em: number | null; // casos.py:356
}

// `parametros` carrega um discriminante `tipo` para folha/investigação; pesquisa NÃO tem `tipo`.
export interface JobParametros {
  tipo?: "folha" | "investigacao"; // api.py:633 (folha), api.py:778 (investigacao)
  [k: string]: unknown;
}

export type JobProgresso = ProgressoPesquisa | ProgressoFolha | ProgressoInvestigacao;
export type JobResultado = ResultadoPesquisa | ResultadoFolha | ResultadoInvestigacao;

// ⚠ W0-F2 — REGRA DE OURO: cada executor grava um dict DIFERENTE no caminho de
// SUCESSO e no de ERRO. Nenhum campo de sucesso é garantido em status "erro".
// Por isso todo campo abaixo é opcional; o único campo garantido em erro é `erro?: string`.

// (1) PESQUISA — POST /pesquisar → _executar_busca_caso
export interface ProgressoPesquisa {
  municipio_atual: string | null; // slug em varredura (null no começo/fim)
  municipios_feitos: number;
  municipios_total: number;
}
export interface ResultadoPesquisa {
  total_itens?: number; // api.py:489 (SÓ no sucesso; ausente no except api.py:495)
  avisos?: string[]; // api.py:489 e 495
  erro?: string; // api.py:495 (só em status erro)
}

// (2) FOLHA — POST /folha → _executar_folha_caso
export interface ProgressoFolha {
  competencia_atual: string | null; // "MM/AAAA" (api.py:577)
  feitas: number;
  total: number;
}
export interface ResultadoFolha {
  itens?: { competencia: string; item_id: string }[]; // api.py:598
  falhas?: { competencia: string; erro: string }[]; // api.py:596
  avisos?: string[]; // api.py:599 (ausente nos dois caminhos de erro)
  erro?: string; // mensagem com candidatos (nome+matrícula), EvidenciaAmbigua
  competencia?: string; // competência onde a ambiguidade ocorreu
}

// (3) INVESTIGAÇÃO — POST /investigar → _executar_investigacao_caso
export interface ProgressoInvestigacao {
  etapa: "planejando" | "concluida" | "erro" | string; // api.py:723,747
  subtarefas_ok?: number; // api.py:748
  lacunas?: number; // api.py:749
}
export interface ResultadoInvestigacao {
  erro?: string | null; // api.py:752 (ramo rico) e api.py:765 (except geral — único campo)
  relatorio_path?: string | null; // api.py:753 (a UI busca via GET /relatorio, não este path)
  subtarefas_ok?: number; // api.py:754
  lacunas?: string[]; // api.py:755
  tokens_total?: number; // api.py:756
  custo_usd?: number; // api.py:757
  teto_atingido?: boolean; // api.py:758
}
