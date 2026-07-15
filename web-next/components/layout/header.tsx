import Link from "next/link";
import { ThemeToggle } from "@/components/theme/theme-toggle";

function BrandMark() {
  return (
    <svg
      width="24"
      height="24"
      viewBox="0 0 32 32"
      fill="none"
      aria-hidden="true"
      className="shrink-0"
    >
      <rect x="6" y="3" width="16" height="20" rx="2" className="fill-primary" />
      <rect x="9" y="7" width="10" height="1.6" rx="0.8" className="fill-primary-foreground" fillOpacity="0.85" />
      <rect x="9" y="11" width="10" height="1.6" rx="0.8" className="fill-primary-foreground" fillOpacity="0.85" />
      <rect x="9" y="15" width="6" height="1.6" rx="0.8" className="fill-primary-foreground" fillOpacity="0.85" />
      <circle cx="21" cy="21" r="6.5" className="fill-background stroke-primary" strokeWidth="2.4" />
      <line x1="25.6" y1="25.6" x2="29.5" y2="29.5" className="stroke-primary" strokeWidth="2.6" strokeLinecap="round" />
    </svg>
  );
}

export function Header() {
  return (
    <header role="banner" className="border-b border-border bg-card">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[var(--z-toast)] focus:rounded-sm focus:bg-primary focus:px-3 focus:py-2 focus:text-primary-foreground"
      >
        Pular para o conteúdo
      </a>
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-4 sm:px-6">
        <Link
          href="/"
          className="inline-flex min-w-0 items-center gap-2 border-b-2 border-accent-brass pb-1 text-base font-medium tracking-tight text-foreground"
        >
          <BrandMark />
          <span className="truncate">
            Busca Transparência <span className="font-semibold text-primary">Goiás</span>
          </span>
        </Link>
        <nav aria-label="Principal" className="flex shrink-0 items-center gap-3 sm:gap-5">
          <Link
            href="/casos"
            className="hidden text-[0.9375rem] text-foreground transition-colors duration-[var(--dur-fast)] ease-[var(--ease-standard)] hover:text-primary sm:inline"
          >
            Casos
          </Link>
          <span aria-hidden="true" className="hidden h-4 w-px bg-border sm:inline-block" />
          <Link
            href="/buscar"
            className="hidden text-[0.9375rem] text-muted-foreground transition-colors duration-[var(--dur-fast)] ease-[var(--ease-standard)] hover:text-primary sm:inline"
          >
            Buscar por seção
          </Link>
          <Link
            href="/pesquisar"
            className="hidden text-[0.9375rem] text-muted-foreground transition-colors duration-[var(--dur-fast)] ease-[var(--ease-standard)] hover:text-primary sm:inline"
          >
            Pesquisar por entidade
          </Link>
          <ThemeToggle />
        </nav>
      </div>
    </header>
  );
}
