/** Chave de localStorage compartilhada entre o ThemeProvider (client) e o
 *  script inline anti-FOUC no layout (server). Em módulo próprio, sem
 *  "use client", para poder ser importada por Componentes de Servidor. */
export const THEME_STORAGE_KEY = "busca-go-theme";
