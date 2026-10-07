FROM public.ecr.aws/docker/library/node:22-slim
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev
COPY server.js ./
EXPOSE 8080
CMD ["node", "--require", "dd-trace/init", "server.js"]
