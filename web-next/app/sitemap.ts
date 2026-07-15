import type { MetadataRoute } from "next";
import type { MunicipioOut } from "@/lib/api-types";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const base = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";
  const staticRoutes: MetadataRoute.Sitemap = [
    { url: `${base}/`, changeFrequency: "daily", priority: 1 },
    { url: `${base}/buscar`, changeFrequency: "daily", priority: 0.8 },
    { url: `${base}/pesquisar`, changeFrequency: "daily", priority: 0.7 },
    { url: `${base}/casos`, changeFrequency: "daily", priority: 0.7 },
  ];
  try {
    // Chama o back para listar municipios. Se falhar, devolve so o static.
    const r = await fetch(`${process.env.BACKEND_URL ?? "http://127.0.0.1:8000"}/api/municipios`, {
      cache: "no-store",
    });
    if (r.ok) {
      const municipios = (await r.json()) as MunicipioOut[];
      return [
        ...staticRoutes,
        ...municipios.map((m) => ({
          url: `${base}/buscar?m=${m.slug}`,
          changeFrequency: "weekly" as const,
          priority: 0.6,
        })),
      ];
    }
  } catch {
    // back offline em build-time: sitemap minimo
  }
  return staticRoutes;
}