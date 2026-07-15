"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

/** Dropdown minimalista (button + menu com state). Sem Radix — para NX4 usamos
 *  o theme toggle (feito separado). Aqui fica pronto para NX5 (export menu). */
interface DropdownMenuProps {
  trigger: React.ReactNode;
  children: React.ReactNode;
  align?: "start" | "end";
}

export function DropdownMenu({ trigger, children, align = "end" }: DropdownMenuProps) {
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef<HTMLDivElement | null>(null);

  React.useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const escHandler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    document.addEventListener("keydown", escHandler);
    return () => {
      document.removeEventListener("mousedown", handler);
      document.removeEventListener("keydown", escHandler);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative inline-block">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "inline-flex h-[38px] w-[38px] items-center justify-center rounded-sm border border-input text-foreground",
          "transition-colors duration-[var(--dur-fast)] ease-[var(--ease-standard)]",
          "hover:bg-muted",
          "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
        )}
      >
        {trigger}
      </button>
      {open && (
        <div
          role="menu"
          className={cn(
            "absolute z-[var(--z-dropdown)] mt-2 min-w-[10rem] origin-top-right rounded-md border border-border bg-card p-1 text-card-foreground shadow-[0_8px_24px_-8px_oklch(0.26_0.02_38_/_0.18)]",
            "duration-[var(--dur-slow)] ease-[var(--ease-out)] animate-in fade-in-0 zoom-in-95",
            align === "end" ? "right-0" : "left-0",
          )}
        >
          {children}
        </div>
      )}
    </div>
  );
}

type DropdownItemProps = React.ButtonHTMLAttributes<HTMLButtonElement>;

export function DropdownItem({ className, ...props }: DropdownItemProps) {
  return (
    <button
      type="button"
      role="menuitem"
      className={cn(
        "block w-full rounded-sm px-3 py-1.5 text-left text-[0.9375rem] text-foreground transition-colors duration-[var(--dur-fast)] ease-[var(--ease-standard)]",
        "hover:bg-muted",
        className,
      )}
      {...props}
    />
  );
}
