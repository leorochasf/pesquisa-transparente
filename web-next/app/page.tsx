import type { Metadata } from "next";
import Link from "next/link";
import { permanentRedirect } from "next/navigation";
import { ChevronRight, Landmark } from "lucide-react";
import { HomeCasosRecentes } from "@/components/home/home-casos-recentes";

interface PageProps {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}

export const metadata: Metadata = {
  title: {
    absolute: "Busca Transparência Goiás — investigação com lastro",
  },
  description:
    "Abra um caso e o Pesquisador varre os portais de transparência de seis municípios goianos, reunindo contratos, dispensas, empenhos e folhas de pagamento num dossiê com o link e o PDF de cada fonte oficial.",
};

/** Deep-links legados da busca antiga (`/?m=…&s=…&f[…]`) preservam o link e o
 *  sitemap: qualquer estado de busca redireciona 308 para `/buscar` com a
 *  mesma querystring (plano §1.3, ⚠ R0-F3). Sem estado de busca, é a home. */
function temEstadoDeBusca(usp: URLSearchParams): boolean {
  if (usp.has("m") || usp.has("s")) return true;
  for (const k of usp.keys()) {
    if (k.startsWith("f[")) return true;
  }
  return false;
}

export default async function Page({ searchParams }: PageProps) {
  const sp = await searchParams;
  const usp = new URLSearchParams();
  for (const [k, v] of Object.entries(sp)) {
    if (typeof v === "string") usp.set(k, v);
    else if (Array.isArray(v)) usp.set(k, v.join(","));
  }

  if (temEstadoDeBusca(usp)) {
    const qs = usp.toString();
    permanentRedirect(qs ? `/buscar?${qs}` : "/buscar");
  }

  return (
    <div className="mx-auto max-w-6xl px-6">
      {/* (A) Frontispício — drama editorial tipográfico, sem foto/gradiente (plano §2-A) */}
      <section className="pt-16 pb-8 sm:pt-24">
        <div aria-hidden="true" className="h-0.5 w-16 rounded-full bg-accent-brass" />
        <h1 className="mt-6 max-w-3xl text-balance text-[2rem] font-semibold tracking-[-0.02em] text-foreground sm:text-[2.75rem]">
          Cada dado do dossiê, com a prova de origem.
        </h1>
        <p className="mt-5 max-w-2xl text-[1.125rem] leading-relaxed text-muted-foreground">
          Abra um caso, descreva o que investiga e o Pesquisador varre os portais de
          transparência de seis municípios goianos — reunindo contratos, dispensas, empenhos e
          folhas de pagamento num único dossiê, com o link da fonte oficial e o PDF de cada
          documento.
        </p>
      </section>

      {/* (B) Painel de casos — o Caso no centro (ilha client, plano §2-B) */}
      <section className="mt-10" aria-label="Casos">
        <HomeCasosRecentes />
      </section>

      {/* (C) Como o Pesquisador monta o dossiê — prosa em 3 colunas, sem cards/ícones (plano §2-C) */}
      <section className="mt-16 sm:mt-20">
        <h2 className="text-[1.3125rem] font-semibold leading-[1.3]">
          Como o Pesquisador monta o dossiê
        </h2>
        <div className="mt-6 grid grid-cols-1 divide-y divide-border sm:grid-cols-3 sm:divide-x sm:divide-y-0">
          <div className="py-6 first:pt-0 sm:px-6 sm:py-0 sm:first:pl-0">
            <h3 className="text-[1.0625rem] font-semibold text-foreground">Investiga.</h3>
            <p className="mt-2 text-[0.9375rem] text-muted-foreground">
              Você descreve o caso — um escritório contratado por dispensa, um servidor cuja
              folha quer quantificar. O assistente planeja a varredura e percorre os seis
              municípios por você.
            </p>
          </div>
          <div className="py-6 sm:px-6 sm:py-0">
            <h3 className="text-[1.0625rem] font-semibold text-foreground">Reúne a evidência.</h3>
            <p className="mt-2 text-[0.9375rem] text-muted-foreground">
              Cada achado vem com lastro: o PDF do documento, quando existe, ou o print e o link
              direto da página oficial quando o dado não é documento — como na folha de
              pagamento.
            </p>
          </div>
          <div className="py-6 last:pb-0 sm:px-6 sm:py-0 sm:last:pr-0">
            <h3 className="text-[1.0625rem] font-semibold text-foreground">Entrega o dossiê.</h3>
            <p className="mt-2 text-[0.9375rem] text-muted-foreground">
              Tudo se organiza num dossiê único, com o relatório pronto e cada linha rastreável
              até a fonte — o material que instrui o procedimento.
            </p>
          </div>
        </div>
      </section>

      {/* (D) Busca direta — ferramentas rebaixadas, baixo peso visual (plano §2-D) */}
      <section className="mt-16 sm:mt-20">
        <h2 className="text-[1.3125rem] font-semibold leading-[1.3]">Busca direta</h2>
        <p className="mt-2 max-w-2xl text-[0.9375rem] text-muted-foreground">
          Para uma consulta pontual, sem abrir um caso, use as buscas diretas nos portais.
        </p>
        <div className="mt-6 divide-y divide-border border-y border-border">
          <Link
            href="/buscar"
            className="group flex items-center justify-between gap-4 py-5 transition-colors duration-[var(--dur-fast)] ease-[var(--ease-standard)] hover:bg-card"
          >
            <span>
              <span className="block text-[1.0625rem] font-semibold text-foreground group-hover:text-primary">
                Buscar por seção
              </span>
              <span className="mt-1 block text-[0.9375rem] text-muted-foreground">
                Percorra licitações, contratos, dispensas ou despesas de um município, seção por
                seção.
              </span>
            </span>
            <ChevronRight className="h-[18px] w-[18px] shrink-0 text-muted-foreground" aria-hidden="true" />
          </Link>
          <Link
            href="/pesquisar"
            className="group flex items-center justify-between gap-4 py-5 transition-colors duration-[var(--dur-fast)] ease-[var(--ease-standard)] hover:bg-card"
          >
            <span>
              <span className="block text-[1.0625rem] font-semibold text-foreground group-hover:text-primary">
                Pesquisar por entidade
              </span>
              <span className="mt-1 block text-[0.9375rem] text-muted-foreground">
                Procure um CNPJ, um servidor ou um termo num município e veja tudo agrupado por
                seção.
              </span>
            </span>
            <ChevronRight className="h-[18px] w-[18px] shrink-0 text-muted-foreground" aria-hidden="true" />
          </Link>
        </div>
      </section>

      {/* (E) Nota de fonte oficial — fecho editorial, Regra do "—" (plano §2-E) */}
      <section className="mt-16 border-t border-border pt-6 pb-16 sm:pb-20">
        <p className="flex max-w-2xl items-start gap-2 text-[0.9375rem] text-muted-foreground">
          <Landmark className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>
            Todos os dados vêm direto dos portais oficiais de transparência (plataforma
            NucleoGov). O Pesquisador não inventa número: quando um dado não existe, a linha
            degrada para &ldquo;—&rdquo; e o que falta aparece nas ressalvas do dossiê.
          </span>
        </p>
      </section>
    </div>
  );
}
