import * as React from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

export type ButtonVariant = "default" | "secondary" | "ghost" | "destructive";
export type ButtonSize = "sm" | "md" | "lg" | "icon";

const TRANSITION = "transition-colors duration-[var(--dur-fast)] ease-[var(--ease-standard)]";

const variantClasses: Record<ButtonVariant, string> = {
  default:
    "bg-primary text-primary-foreground hover:bg-primary-hover hover:shadow-[0_1px_2px_oklch(0.26_0.02_38_/_0.10)] active:bg-primary-active active:shadow-none disabled:bg-muted disabled:text-muted-foreground disabled:shadow-none",
  secondary:
    "border border-input bg-card text-foreground hover:bg-muted active:border-foreground disabled:border-border disabled:bg-card disabled:text-muted-foreground",
  ghost:
    "bg-transparent text-foreground hover:bg-muted disabled:text-muted-foreground",
  destructive: "bg-destructive text-destructive-foreground hover:opacity-90 active:opacity-80",
};

const sizeClasses: Record<ButtonSize, string> = {
  sm: "h-8 px-3 text-sm",
  md: "h-[38px] px-4 text-[0.9375rem]",
  lg: "h-11 px-5 text-[0.9375rem]",
  icon: "h-[38px] w-[38px]",
};

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  function Button(
    { className, variant = "default", size = "md", loading = false, disabled, children, ...props },
    ref,
  ) {
    return (
      <button
        ref={ref}
        disabled={disabled || loading}
        aria-busy={loading || undefined}
        className={cn(
          "inline-flex items-center justify-center gap-2 rounded-sm font-semibold",
          TRANSITION,
          "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
          "disabled:pointer-events-none disabled:cursor-not-allowed",
          variantClasses[variant],
          sizeClasses[size],
          className,
        )}
        {...props}
      >
        {loading && <Loader2 className="h-4 w-4 shrink-0 animate-spin" aria-hidden="true" />}
        {children}
      </button>
    );
  },
);
