# syntax=docker/dockerfile:1

# ── Build the standalone Vue SPA ─────────────────────────────────────────────
FROM node:24-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Empty base url -> the SPA calls the API with relative paths, served same-origin
# by nginx (no CORS). Override at build time for a split-origin deployment.
ARG VITE_API_BASE_URL=
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN BUILD_TARGET=standalone npx vite build

# ── Serve the SPA and reverse-proxy the backend ──────────────────────────────
FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
