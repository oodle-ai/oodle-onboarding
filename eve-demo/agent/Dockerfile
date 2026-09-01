FROM node:24-slim

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --no-fund --no-audit

COPY tsconfig.json ./
COPY agent ./agent

RUN npx eve build

EXPOSE 8098
CMD ["npx", "eve", "start"]
