FROM node:22-slim

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --omit=dev

COPY instrumentation.js logger.js server.js ./

EXPOSE 8100
CMD ["npm", "start"]
