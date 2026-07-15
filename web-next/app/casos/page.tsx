import type { Metadata } from "next";
import { CasosLista } from "@/components/casos/casos-lista";

export const metadata: Metadata = {
  title: "Casos · Transparência Goiás",
  description: "Lista de casos e dossiês de investigação — crie um novo caso ou abra um existente.",
};

export default function CasosPage() {
  return (
    <div className="mx-auto max-w-6xl px-6 py-10">
      <header className="mb-8 border-b border-border pb-8">
        <h1 className="text-[1.625rem] font-semibold leading-[1.25] tracking-[-0.01em] sm:text-[1.9rem]">
          Casos
        </h1>
        <p className="mt-2 max-w-2xl text-[0.9375rem] text-muted-foreground">
          Cada caso reúne os alvos, as pesquisas, as evidências coletadas e o dossiê final de uma
          investigação.
        </p>
      </header>

      <CasosLista />
    </div>
  );
}
