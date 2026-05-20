FROM node:20-slim AS build

WORKDIR /app

# D7.1 §H2.5 — copy the lockfile and use `npm ci` so a transitive bump on
# npm (e.g. react-globe.gl) cannot break our build until the change is
# explicitly committed to package-lock.json. `npm ci` refuses to install
# if it would mutate the lockfile.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:1.27-alpine AS runtime
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 4173
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -qO- http://localhost/ >/dev/null || exit 1
