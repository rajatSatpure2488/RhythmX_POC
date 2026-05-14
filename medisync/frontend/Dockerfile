# ============================================
# MediSync Frontend — Dockerfile
# React + Vite (dev & production)
# ============================================

# ── Stage 1: Install dependencies ────────────
FROM node:20-alpine AS deps

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci --silent


# ── Stage 2: Build for production ────────────
FROM node:20-alpine AS builder

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

RUN npm run build


# ── Stage 3: Production (Nginx) ──────────────
FROM nginx:alpine AS production

LABEL maintainer="MediSync Team"
LABEL description="MediSync React Frontend — Clinical Documentation UI"
LABEL version="1.0.0"

# Copy built assets to Nginx
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy custom Nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -q --spider http://localhost:80/ || exit 1

CMD ["nginx", "-g", "daemon off;"]


# ── Stage 4: Development (Vite dev server) ───
FROM node:20-alpine AS development

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

EXPOSE 8501

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
