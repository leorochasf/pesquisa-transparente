import { Badge } from "@/components/ui/badge";
import { rotuloTipo, MUNICIPIOS_CASO } from "@/components/casos/caso-tipo";
import type { CasoDetalhe } from "@/lib/casos-types";

const NOME_MUNICIPIO = new Map<string, string>(MUNICIPIOS_CASO.map((m) => [m.value, m.label]));

function rotuloMunicipio(slug: string): string {
  return NOME_MUNICIPIO.get(slug) ?? slug;
}

function alvoTexto(caso: CasoDetalhe): string {
  const { nome, cnpj, servidor } = caso.alvos;
  const partes = [
    nome ? `nome: ${nome}` : null,
    cnpj ? `CNPJ: ${cnpj}` : null,
    servidor ? `servidor: ${servidor}` : null,
  ].filter((v): v is string => Boolean(v));
  return partes.join(" · ");
}

function formatarDataHora(epochSegundos: number): string {
  return new Date(epochSegundos * 1000).toLocaleString("pt-BR");
}

/** Seção 1 do dossiê (plano §1.2): título, tipo, municípios, alvos,
 *  criado/atualizado em. Sem hero-metric (DESIGN.md §6, proibido). */
export function DossieCabecalho({ caso }: { caso: CasoDetalhe }) {
  const alvo = alvoTexto(caso);

  return (
    <header className="border-b border-border pb-6">
      <h1 className="text-[1.625rem] font-semibold leading-[1.25] tracking-[-0.01em] sm:text-[1.9rem]">
        {caso.titulo}
      </h1>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Badge variant="secondary">{rotuloTipo(caso.tipo)}</Badge>
        {caso.municipios.map((slug) => (
          <Badge key={slug} variant="secondary">
            {rotuloMunicipio(slug)}
          </Badge>
        ))}
      </div>
      <p className="mt-3 font-mono text-[0.8125rem] tabular-nums text-muted-foreground">
        {alvo || <span>—</span>}
      </p>
      <p className="mt-2 text-[0.8125rem] text-muted-foreground">
        Criado em <span className="font-mono tabular-nums">{formatarDataHora(caso.criado_em)}</span>
        {" · "}
        Atualizado em{" "}
        <span className="font-mono tabular-nums">{formatarDataHora(caso.atualizado_em)}</span>
      </p>
    </header>
  );
}
