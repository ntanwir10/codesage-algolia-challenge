# Stage 1: build the Vite bundle
FROM node:22-alpine AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Vite inlines these at build time.
ARG VITE_API_BASE_URL=/api/v1
ARG VITE_WEBSOCKET_URL=ws://localhost/ws
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_WEBSOCKET_URL=$VITE_WEBSOCKET_URL
RUN npm run build

# Stage 2: nginx serves dist. The reverse-proxy config (deployment/nginx.conf)
# is mounted over /etc/nginx/nginx.conf by compose.
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
