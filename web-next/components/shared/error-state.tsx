import { AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ErrorStateProps {
  title?: string;
  message: string;
  onRetry?: () => void;
}

export function ErrorState({ title = "Erro", message, onRetry }: ErrorStateProps) {
  return (
    <div
      role="alert"
      className="rounded-md border border-destructive bg-destructive-tint p-4 text-foreground"
    >
      <div className="flex gap-3">
        <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-destructive" aria-hidden="true" />
        <div>
          <p className="text-[1.0625rem] font-semibold leading-[1.35]">{title}</p>
          <p className="mt-1 text-[0.9375rem]">{message}</p>
          {onRetry && (
            <Button type="button" variant="secondary" size="sm" onClick={onRetry} className="mt-3">
              Tentar de novo
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
