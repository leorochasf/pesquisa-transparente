/**
 * BUG-16: une a lista de secoes descoberta ao vivo com a secao ativa
 * (vinda da URL/busca), para o select nunca esconder silenciosamente
 * a secao que de fato foi buscada.
 */
export function composeSecaoOptions(
  secoes: string[] | null,
  secaoAtiva: string,
): string[] {
  const base = secoes ?? [];
  if (secaoAtiva && !base.includes(secaoAtiva)) {
    return [...base, secaoAtiva].sort((a, b) => a.localeCompare(b));
  }
  return base;
}
