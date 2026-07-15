/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // /api/* e servido pelos route handlers em app/api/* (ver lib/backend-proxy.ts),
  // que proxiam para o back FastAPI com tratamento de erro. Nao usar rewrites()
  // aqui: para rotas dinamicas (app/api/secoes/[slug], app/api/buscar/[slug]/[secao])
  // um rewrite em "afterFiles" e checado ANTES do route handler dinamico e o
  // sequestraria, pulando o tratamento de erro (502 amigavel) implementado nele.
  typedRoutes: true,
};

export default nextConfig;
