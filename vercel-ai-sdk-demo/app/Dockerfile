FROM node:24-slim

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --no-fund --no-audit

COPY src ./src

EXPOSE 8097
CMD ["npm", "start"]
