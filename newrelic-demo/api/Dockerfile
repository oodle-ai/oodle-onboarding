FROM node:22-alpine
WORKDIR /app
COPY package.json .
RUN npm install --omit=dev
COPY app.js .
# both the New Relic agent and the OTel SDK hook the same process; app.js has no agent code
CMD ["node", "-r", "newrelic", "-r", "@opentelemetry/auto-instrumentations-node/register", "app.js"]
