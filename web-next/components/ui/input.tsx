import * as React from "react";
import { cn } from "@/lib/utils";

export const Input = React.forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement>
>(function Input({ className, type = "text", ...props }, ref) {
  return (
    <input
      ref={ref}
      type={type}
      className={cn(
        "block h-[38px] w-full rounded-sm border border-input bg-background px-3 text-[0.9375rem] text-foreground",
        "transition-colors duration-[var(--dur-fast)] ease-[var(--ease-standard)]",
        "placeholder:text-muted-foreground",
        "hover:border-foreground",
        "focus-visible:border-ring focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
        "disabled:cursor-not-allowed disabled:border-border disabled:bg-muted disabled:text-muted-foreground disabled:hover:border-border",
        "aria-[invalid=true]:border-destructive",
        className,
      )}
      {...props}
    />
  );
});
