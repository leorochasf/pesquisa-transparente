export function Footer() {
  const year = new Date().getFullYear();
  return (
    <footer role="contentinfo" className="mt-16 border-t border-border bg-card">
      <div className="mx-auto flex max-w-6xl flex-col gap-2 px-6 py-6 text-[0.9375rem] text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
        <p>
          Dados direto da fonte oficial (plataforma{" "}
          <a
            href="https://nucleogov.com"
            target="_blank"
            rel="noopener noreferrer"
            className="underline underline-offset-2 hover:text-primary"
          >
            NucleoGov
          </a>
          ) · {year}
        </p>
        <p>
          <a
            href="https://github.com/"
            target="_blank"
            rel="noopener noreferrer"
            className="underline underline-offset-2 hover:text-primary"
          >
            Código-fonte
          </a>
        </p>
      </div>
    </footer>
  );
}
