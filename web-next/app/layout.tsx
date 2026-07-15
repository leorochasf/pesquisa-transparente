import type { Metadata } from "next";
import { IBM_Plex_Sans, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";
import { ThemeProvider } from "@/components/theme/theme-provider";
import { Header } from "@/components/layout/header";
import { Footer } from "@/components/layout/footer";
import { THEME_STORAGE_KEY } from "@/lib/theme-constants";

const plexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-plex-sans",
  display: "swap",
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-plex-mono",
  display: "swap",
});

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

export const metadata: Metadata = {
  title: {
    default: "Busca Transparência Goiás",
    template: "%s · Busca Transparência",
  },
  description:
    "Hub de consulta de transparência pública dos municípios goianos (portal nucleogov).",
  metadataBase: new URL(SITE_URL),
  openGraph: {
    title: "Busca Transparência Goiás",
    description: "Consulta unificada de transparência pública de Goiás.",
    type: "website",
  },
};

// Aplica a classe "dark" antes do primeiro paint (evita FOUC), lendo a
// mesma chave de localStorage/preferência do sistema que o ThemeProvider.
// Renderizado como <script> cru (não via next/script) porque precisa ser um
// script inline bloqueante de verdade no HTML inicial: next/script mesmo com
// strategy="beforeInteractive" apenas enfileira o código para ser executado
// pelo bundle JS do Next (async), o que não impede o flash em conexões lentas.
const themeInitScript = `(function(){try{var t=localStorage.getItem(${JSON.stringify(
  THEME_STORAGE_KEY,
)});var d=t==="dark"||(t!=="light"&&window.matchMedia("(prefers-color-scheme: dark)").matches);if(d){document.documentElement.classList.add("dark");}}catch(e){}})();`;

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="pt-BR"
      suppressHydrationWarning
      className={`${plexSans.variable} ${plexMono.variable}`}
    >
      <body className="flex min-h-screen flex-col">
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
        <ThemeProvider>
          <Header />
          <main id="main" className="flex-1">
            {children}
          </main>
          <Footer />
        </ThemeProvider>
      </body>
    </html>
  );
}