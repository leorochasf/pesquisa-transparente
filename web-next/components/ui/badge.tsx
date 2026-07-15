import * as React from "react";
import { cn } from "@/lib/utils";

type BadgeVariant =
  | "default"
  | "secondary"
  | "outline"
  | "success"
  | "warning"
  | "info"
  | "destructive";

const variants: Record<BadgeVariant, string> = {
  default: "bg-muted text-muted-foreground",
  secondary: "bg-muted text-muted-foreground",
  outline: "border border-border bg-transparent text-foreground",
  success: "bg-success-tint text-success",
  warning: "bg-warning-tint text-warning",
  info: "bg-info-tint text-info",
  destructive: "bg-destructive-tint text-destructive",
};

const DOT_COLOR: Partial<Record<BadgeVariant, string>> = {
  success: "bg-success",
  warning: "bg-warning",
  info: "bg-info",
  destructive: "bg-destructive",
};

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
  dot?: boolean;
}

export function Badge({
  className,
  variant = "default",
  dot = false,
  children,
  ...props
}: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[0.6875rem] font-medium uppercase leading-[1.2] tracking-[0.06em]",
        variants[variant],
        className,
      )}
      {...props}
    >
      {dot && (
        <span
          className={cn("h-1.5 w-1.5 shrink-0 rounded-full", DOT_COLOR[variant] ?? "bg-current")}
          aria-hidden="true"
        />
      )}
      {children}
    </span>
  );
}
