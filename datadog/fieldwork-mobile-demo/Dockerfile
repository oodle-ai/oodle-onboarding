FROM node:22.20.0-bookworm-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts
COPY server ./server
COPY src/shared ./src/shared
RUN npx tsc -p server/tsconfig.json --outDir /app/build

FROM node:22.20.0-bookworm-slim
WORKDIR /app
ENV NODE_ENV=production HOST=0.0.0.0 PORT=4310
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/build ./build
USER node
EXPOSE 4310
CMD ["node", "build/server/index.js"]
