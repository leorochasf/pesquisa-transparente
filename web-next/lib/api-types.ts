/** Tipos que refletem a API HTTP do back (FastAPI, busca_go/api.py). */

export interface MunicipioOut {
  slug: string;
  nome: string;
  plataforma: string;
  url_base: string;
}

export interface SecoesResponse {
  slug: string;
  secoes: string[];
  note?: string; // quando plataforma != sgp
}

export interface ConfigResponse {
  cache_db: string;
  cache_days: number;
  headless: boolean;
  timeout_ms: number;
  // catalogo canonico e estatico de secoes (sem scraping); pode nao existir
  // ainda em backends antigos — sempre trate como opcional.
  secoes_catalogo?: string[];
}

export interface FiltrosBusca {
  ano?: number;
  cnpj?: string;
  modalidade?: string;
  numero?: string;
  credor?: string;
}

/** Cada registro de transparência. Colunas dinâmicas do nucleogov. */
export interface ItemTransparencia {
  [key: string]: unknown;
  titulo?: string;
  data?: string;
  valor?: string | number;
  credor?: string;
  cnpj?: string;
  modalidade?: string;
  numero?: string;
  link?: string;
}

export interface BuscaResponse {
  items: ItemTransparencia[];
  cached: boolean;
  source_url: string;
}

/** Tipos da BUSCA POR ENTIDADE (busca_go/nucleo/entidade.py::pesquisar). */

export type TipoEntidade = "cpf" | "cnpj" | "termo";

/** Identificadores do registro, preservados para o passo lazy de anexos. */
export interface RefRegistro {
  id?: string | null;
  numero?: string | null;
  ano?: string | null;
}

/** Item de contratos/licitacoes/dispensas normalizado pelo backend. */
export interface ItemEntidade {
  titulo?: string;
  descricao?: string;
  fornecedor?: string;
  documento?: string;
  valor?: string;
  data?: string;
  tem_aditivo?: boolean;
  ref_registro?: RefRegistro;
  // true = anexos ja confirmados na listagem; false/null = so se sabe sob demanda.
  tem_anexos?: boolean | null;
  raw?: unknown;
}

/** Um documento anexo a um registro (contrato/licitacao/dispensa). */
export interface AnexoOut {
  rotulo: string;
  ref: string;
}

/** Linha de folha (um mes/tipo de um servidor). */
export interface ItemFolha {
  matricula?: string;
  nome?: string;
  cargo?: string;
  lotacao?: string;
  orgao?: string;
  vinculo?: string;
  referencia?: string;
  tipo_folha?: string;
  ano?: string;
  mes?: string;
  proventos?: string;
  descontos?: string;
  liquido?: string;
  cpf_mascarado?: string;
  raw?: unknown;
}

/** Servidor agrupado por matricula, com as folhas do periodo pesquisado. */
export interface ServidorFolha {
  matricula: string;
  nome: string;
  cargo: string;
  lotacao: string;
  orgao: string;
  folhas: ItemFolha[];
}

export type SecaoEntidade = "contratos" | "licitacoes" | "dispensas" | "folha";

export interface GrupoEntidade {
  secao: SecaoEntidade;
  modo: "server" | "varredura";
  total: number;
  total_portal: number;
  truncado: boolean;
  itens: (ItemEntidade | ItemFolha)[];
  servidores?: ServidorFolha[];
}

export interface PesquisaEntidadeResponse {
  tipo: TipoEntidade;
  termo: string;
  municipio: { slug: string; nome: string };
  grupos: GrupoEntidade[];
  avisos: string[];
}
