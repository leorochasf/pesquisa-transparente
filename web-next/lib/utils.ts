/** cn() compatível com a convenção do shadcn/ui:
 *  combina clsx (lógica condicional) + tailwind-merge (resolve conflitos Tailwind). */
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}