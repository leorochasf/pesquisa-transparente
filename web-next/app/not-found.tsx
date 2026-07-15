import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center px-6 text-center">
      <p className="font-mono text-7xl font-semibold tabular-nums text-muted-foreground/40">404</p>
      <h1 className="mt-4 text-[1.625rem] font-semibold leading-[1.25] tracking-[-0.01em]">
        Página não encontrada
      </h1>
      <p className="mt-2 text-[0.9375rem] text-muted-foreground">
        A página que você procura não existe ou foi movida.
      </p>
      <Link
        href="/"
        className="mt-6 inline-flex h-[38px] items-center justify-center rounded-sm border border-input bg-card px-4 text-[0.9375rem] font-semibold text-foreground transition-colors duration-[var(--dur-fast)] ease-[var(--ease-standard)] hover:bg-muted focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
      >
        Voltar para busca
      </Link>
    </div>
  );
}
