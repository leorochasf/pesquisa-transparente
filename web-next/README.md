# Busca Transparência Goiás — Frontend

Next.js 15 + TypeScript + Tailwind CSS v3 + shadcn/ui.

## Setup

### 1. Dependências

```bash
# usa pnpm (não npm nem yarn)
corepack enable
pnpm install
```

> Requer Node ≥ 20.9.0.

### 2. Variáveis de ambiente

Copie `.env.example` para `.env.local`:

```bash
cp .env.example .env.local
```

| Variável | Padrão | Descrição |
|---|---|---|
| `BACKEND_URL` | `http://127.0.0.1:8765` | URL do back FastAPI |

### 3. Desenvolver

```bash
pnpm dev        # http://localhost:3000
```

### 4. Produzir

```bash
pnpm build
pnpm start
```

### 5. Testar

```bash
pnpm test
pnpm lint
pnpm tsc --noEmit
```

## Arquitetura

- **`app/`** — rotas App Router (Next.js 15)
- **`app/page.tsx`** — página principal com busca + resultados
- **`app/municipio/[slug]/page.tsx`** — página de municipio (SEO)
- **`components/`** — componentes React (shadcn/ui + custom)
- **`lib/`** — utilitários: tipos da API, hooks, utils

## Proxy em dev

Em `next.config.ts`, `/api/*` é redirecionado para `BACKEND_URL/api/*`.
Em produção, configure o proxy reverso (nginx/Caddy) para redirecionar.

## shadcn/ui

Componentes adicionados com `pnpm dlx shadcn@latest add <component>`.
Não edite arquivos em `components/ui/` — recrie com `shadcn add`.
