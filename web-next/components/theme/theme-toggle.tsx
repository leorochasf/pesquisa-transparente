"use client";

import { Sun, Moon, Monitor, Check } from "lucide-react";
import { useTheme } from "./theme-provider";
import { DropdownMenu, DropdownItem } from "@/components/ui/dropdown-menu";

const OPTIONS = [
  { value: "light" as const, label: "Claro", icon: Sun },
  { value: "dark" as const, label: "Escuro", icon: Moon },
  { value: "system" as const, label: "Sistema", icon: Monitor },
];

/** Alterna entre claro/escuro/sistema. Acessível via menu (aria-haspopup, role="menu"). */
export function ThemeToggle() {
  const { theme, resolved, setTheme } = useTheme();
  const CurrentIcon = theme === "system" ? Monitor : resolved === "dark" ? Moon : Sun;

  return (
    <DropdownMenu
      align="end"
      trigger={
        <>
          <CurrentIcon className="h-4 w-4" aria-hidden="true" />
          <span className="sr-only">Alternar tema</span>
        </>
      }
    >
      {OPTIONS.map(({ value, label, icon: Icon }) => (
        <DropdownItem
          key={value}
          onClick={() => setTheme(value)}
          aria-current={theme === value}
          className="flex items-center gap-2"
        >
          <Icon className="h-4 w-4" aria-hidden="true" />
          <span className="flex-1">{label}</span>
          {theme === value && <Check className="h-4 w-4" aria-hidden="true" />}
        </DropdownItem>
      ))}
    </DropdownMenu>
  );
}
