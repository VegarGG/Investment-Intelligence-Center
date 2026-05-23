FROM node:20-slim AS build

WORKDIR /app

# D9 §4.2 — build context is repo root, so paths are prefixed with
# apps/dashboard/.

# D7.1 §H2.5 — copy the lockfile and use `npm ci` so a transitive bump on
# npm (e.g. react-globe.gl) cannot break our build until the change is
# explicitly committed to package-lock.json. `npm ci` refuses to install
# if it would mutate the lockfile.
COPY apps/dashboard/package.json apps/dashboard/package-lock.json ./
RUN npm ci

COPY apps/dashboard/ ./
RUN npm run build

# D9 §4.2 — build-time assertion that the SPA actually produced index.html.
# Catches the "container is up but docroot is empty" failure mode (N3 in §4.1).
RUN test -f /app/dist/index.html || (echo "no index.html in dashboard dist/" >&2 && exit 1)

FROM nginx:1.27-alpine AS runtime
# D9 §4.2 — replace nginx's default site with our SPA-aware config.
# Default config has `try_files $uri =404`, which 404s every React Router
# sub-route on hard refresh (e.g. /map). The IIC config adds SPA fallback
# + /api/* reverse proxies for every agent the dashboard actually calls.
COPY infra/nginx/dashboard.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 4173
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -qO- http://localhost/ >/dev/null || exit 1
