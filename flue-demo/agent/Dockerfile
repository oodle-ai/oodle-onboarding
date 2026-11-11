FROM node:24-slim

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --no-fund --no-audit

COPY tsconfig.json flue.config.ts vite.config.ts ./
COPY src ./src
COPY scripts ./scripts

RUN npx vite build

ENV PORT=8099
EXPOSE 8099
# Exec form, so SIGTERM reaches the Flue server and it stops cleanly.
CMD ["node", "dist/server.mjs"]
