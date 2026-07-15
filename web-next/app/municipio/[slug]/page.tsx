import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ExternalLink } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import type { MunicipioOut, SecoesResponse } from "@/lib/api-types";

interface Props {
  params: Promise<{ slug: string }>;
}

const BACKEND = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

async function getMunicipio(slug: string): Promise<MunicipioOut | null> {
  try {
    const r = await fetch(`${BACKEND}/api/municipios`, { cache: "no-store" });
    if (!r.ok) return null;
    const municipios = (await r.json()) as MunicipioOut[];
    return municipios.find((m) => m.slug === slug) ?? null;
  } catch {
    return null;
  }
}

async function getSecoes(slug: string): Promise<SecoesResponse | null> {
  try {
    const r = await fetch(`${BACKEND}/api/secoes/${slug}`, { cache: "no-store" });
    if (!r.ok) return null;
    return (await r.json()) as SecoesResponse;
  } catch {
    return null;
  }
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const mun = await getMunicipio(slug);
  if (!mun) return { title: "Município não encontrado" };
  return {
    title: `${mun.nome} · Transparência`,
    description: `Dados de transparência pública de ${mun.nome}.`,
    openGraph: {
      title: `${mun.nome} · Transparência`,
      description: `Dados de transparência pública de ${mun.nome}.`,
    },
  };
}

export default async function MunicipioPage({ params }: Props) {
  const { slug } = await params;
  const mun = await getMunicipio(slug);
  if (!mun) notFound();
  const secoes = await getSecoes(slug);

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="text-[1.625rem] font-semibold leading-[1.25] tracking-[-0.01em]">
        {mun.nome}
      </h1>
      <p className="mt-2 text-[0.9375rem] text-muted-foreground">
        Plataforma: <strong className="font-medium text-foreground">{mun.plataforma}</strong> ·{" "}
        <a
          href={mun.url_base}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-primary underline underline-offset-2 hover:text-primary-hover"
        >
          portal oficial
          <ExternalLink className="h-3 w-3" aria-hidden="true" />
        </a>
      </p>

      <Card className="mt-8">
        <CardContent className="p-6">
          <h2 className="text-[1.0625rem] font-semibold leading-[1.35]">Seções disponíveis</h2>
          {secoes ? (
            <ul className="mt-3 space-y-1.5">
              {secoes.secoes.map((s) => (
                <li key={s}>
                  <a
                    href={`/?m=${mun.slug}&s=${s}`}
                    className="text-primary underline underline-offset-2 hover:text-primary-hover"
                  >
                    {s}
                  </a>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-[0.9375rem] text-muted-foreground">
              Não foi possível listar as seções agora.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
