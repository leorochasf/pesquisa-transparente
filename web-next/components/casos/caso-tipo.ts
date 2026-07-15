/** Mapa `tipo → rótulo pt-BR de jurista` (plano §1.1). A UI restringe a
 *  criação a estas três opções; `tipo` é livre no backend (`api.py::CasoIn`
 *  não restringe), então `rotuloTipo` cai num rótulo genérico para valores
 *  fora do catálogo (defensivo, W3 pode reusar em `dossie-cabecalho.tsx`). */
export const TIPOS_CASO = [
  { value: "dispensa_advocacia", label: "Dispensa / inexigibilidade (advocacia)" },
  { value: "dano_erario_folha", label: "Dano ao erário — folha de servidor" },
  { value: "livre", label: "Investigação livre" },
] as const;

export type TipoCaso = (typeof TIPOS_CASO)[number]["value"];

export function rotuloTipo(tipo: string): string {
  return TIPOS_CASO.find((t) => t.value === tipo)?.label ?? tipo;
}

/** Municípios cobertos, validados no backend (`api.py::_validar_municipios`,
 *  plano §0). A UI nunca oferece município fora destes sete. */
export const MUNICIPIOS_CASO = [
  { value: "caldazinha", label: "Caldazinha" },
  { value: "cristalina", label: "Cristalina" },
  { value: "itumbiara", label: "Itumbiara" },
  { value: "rioverde", label: "Rio Verde" },
  { value: "saomigueldoaraguaia", label: "São Miguel do Araguaia" },
  { value: "senadorcanedo", label: "Senador Canedo" },
  { value: "trindade", label: "Trindade" },
] as const;
