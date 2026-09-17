FROM node:24-slim

RUN apt-get update \
  && apt-get install -y --no-install-recommends ca-certificates git \
  && rm -rf /var/lib/apt/lists/*

# The real CLI, straight from npm. OpenCode installs the plugin
# named in opencode.json on its first start.
ARG OPENCODE_VERSION=latest
RUN npm i -g --no-audit --no-fund "opencode-ai@${OPENCODE_VERSION}"

# Which opencode.json to ship: `opencode` (the plugin) or
# `opencode-native` (OpenCode's own OTLP export, the repro).
ARG OPENCODE_CONFIG_DIR=opencode
COPY ${OPENCODE_CONFIG_DIR}/opencode.json /root/.config/opencode/opencode.json

WORKDIR /workspace
