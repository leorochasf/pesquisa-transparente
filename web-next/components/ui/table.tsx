import * as React from "react";
import { cn } from "@/lib/utils";

/** Wrapper sobre <table> com classes Tailwind. Acessibilidade fica com o caller
 *  (caption, scope, thead/tbody). */

export const Table = React.forwardRef<
  HTMLTableElement,
  React.TableHTMLAttributes<HTMLTableElement>
>(function Table({ className, ...props }, ref) {
  return (
    <div className="w-full overflow-x-auto rounded-md border border-border">
      <table
        ref={ref}
        className={cn("w-full border-collapse text-[0.9375rem]", className)}
        {...props}
      />
    </div>
  );
});

export const THead = React.forwardRef<
  HTMLTableSectionElement,
  React.HTMLAttributes<HTMLTableSectionElement>
>(function THead({ className, ...props }, ref) {
  return (
    <thead
      ref={ref}
      className={cn(
        "sticky top-0 z-[var(--z-sticky)] border-b border-border bg-card text-left",
        className,
      )}
      {...props}
    />
  );
});

export const TBody = React.forwardRef<
  HTMLTableSectionElement,
  React.HTMLAttributes<HTMLTableSectionElement>
>(function TBody({ className, ...props }, ref) {
  return <tbody ref={ref} className={cn("bg-background", className)} {...props} />;
});

export const TR = React.forwardRef<
  HTMLTableRowElement,
  React.HTMLAttributes<HTMLTableRowElement>
>(function TR({ className, ...props }, ref) {
  return (
    <tr
      ref={ref}
      className={cn(
        "group border-b border-border last:border-0 transition-colors duration-[var(--dur-fast)] ease-[var(--ease-standard)] hover:bg-muted",
        className,
      )}
      {...props}
    />
  );
});

interface THProps extends React.ThHTMLAttributes<HTMLTableCellElement> {
  stickyLeft?: boolean;
}

export const TH = React.forwardRef<HTMLTableCellElement, THProps>(function TH(
  { className, stickyLeft = false, ...props },
  ref,
) {
  return (
    <th
      ref={ref}
      scope="col"
      className={cn(
        "px-3 py-2 text-[0.6875rem] font-medium uppercase leading-[1.2] tracking-[0.06em] text-muted-foreground",
        stickyLeft && "sticky left-0 z-[1] bg-card max-lg:shadow-[1px_0_0_0_var(--border)]",
        className,
      )}
      {...props}
    />
  );
});

interface TDProps extends React.TdHTMLAttributes<HTMLTableCellElement> {
  stickyLeft?: boolean;
}

export const TD = React.forwardRef<HTMLTableCellElement, TDProps>(function TD(
  { className, stickyLeft = false, ...props },
  ref,
) {
  return (
    <td
      ref={ref}
      className={cn(
        "px-3 py-2 align-top text-foreground",
        stickyLeft &&
          "sticky left-0 z-[1] bg-background max-lg:shadow-[1px_0_0_0_var(--border)] group-hover:bg-muted",
        className,
      )}
      {...props}
    />
  );
});
