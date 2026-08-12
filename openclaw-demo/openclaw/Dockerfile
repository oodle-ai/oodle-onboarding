FROM node:24-slim

RUN apt-get update \
  && apt-get install -y --no-install-recommends ca-certificates \
  && rm -rf /var/lib/apt/lists/*

# The real CLI + gateway, straight from npm.
ARG OPENCLAW_VERSION=latest
RUN npm i -g --no-audit --no-fund "openclaw@${OPENCLAW_VERSION}"

# The tracing plugin, with its own node_modules so the Langfuse and OTel
# packages resolve when OpenClaw loads it.
WORKDIR /plugin
COPY plugin/package.json ./package.json
RUN npm install --no-audit --no-fund --omit=dev
COPY plugin/index.js plugin/openclaw.plugin.json ./

COPY openclaw/entrypoint.sh /usr/local/bin/entrypoint.sh
COPY openclaw/openclaw.json /seed/openclaw.json
RUN chmod +x /usr/local/bin/entrypoint.sh

ENV OPENCLAW_STATE_DIR=/state
WORKDIR /state
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
