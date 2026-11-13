FROM node:22-alpine@sha256:1314fb30ec37592d5845e5a160d522c0e680972aa534549940b8d73bde88481a AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine@sha256:65e3e85dbaed8ba248841d9d58a899b6197106c23cb0ff1a132b7bfe0547e4c0
USER root
RUN rm -f /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx/base.inc nginx/off.conf nginx/tls.conf nginx/security-headers.inc nginx/app-locations.inc /opt/redshadow/nginx/
COPY --chmod=0755 nginx/40-select-tls-mode.sh /docker-entrypoint.d/40-select-tls-mode.sh
RUN chown -R 101:0 /etc/nginx/conf.d && chmod -R g+w /etc/nginx/conf.d
USER 101
