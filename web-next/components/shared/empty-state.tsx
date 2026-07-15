import { FileSearch, type LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";

interface EmptyStateProps {
  title: string;
  description?: string;
  icon?: LucideIcon;
  actionLabel?: string;
  onAction?: () => void;
}

export function EmptyState({
  title,
  description,
  icon: Icon = FileSearch,
  actionLabel,
  onAction,
}: EmptyStateProps) {
  return (
    <div className="rounded-md border border-border bg-card p-8 text-center">
      <Icon className="mx-auto h-8 w-8 text-muted-foreground" aria-hidden="true" />
      <p className="mt-3 text-[1.0625rem] font-semibold leading-[1.35]">{title}</p>
      {description && (
        <p className="mt-1 text-[0.9375rem] text-muted-foreground">{description}</p>
      )}
      {actionLabel && onAction && (
        <Button type="button" variant="ghost" onClick={onAction} className="mt-4">
          {actionLabel}
        </Button>
      )}
    </div>
  );
}
