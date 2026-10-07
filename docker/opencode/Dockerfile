# syntax=docker/dockerfile:1.7
# OpenCode is installed while building the image, never during container start.
# Updating it is an explicit reviewed change through OPENCODE_VERSION.
FROM docker:27.5.1-cli@sha256:851f91d241214e7c6db86513b270d58776379aacc5eb9c4a87e5b47115e3065c AS docker-cli

FROM node:22-bookworm-slim

ARG OPENCODE_VERSION=1.18.19

RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates python3 \
 && rm -rf /var/lib/apt/lists/* \
 && npm install --global --omit=dev "opencode-ai@${OPENCODE_VERSION}" \
 && mkdir -p /home/node/.config/opencode \
 && chown -R node:node /home/node

# Existing workspaces start the token-savior MCP with uvx. Keep the runtime
# available in both ARM64 (Oracle) and AMD64 (CI) images without downloading
# Python or installing a package at container startup.
COPY --from=ghcr.io/astral-sh/uv:0.12.18 /uv /uvx /usr/local/bin/
COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker
ENV UV_PYTHON_DOWNLOADS=never

COPY start.sh /usr/local/bin/start-opencode
COPY launcher.js /usr/local/bin/opencode-launcher.js
COPY smoke.js /usr/local/bin/opencode-smoke.js
RUN chmod 0555 /usr/local/bin/start-opencode

USER node:node
WORKDIR /workspaces

EXPOSE 4096

ENTRYPOINT ["/usr/local/bin/start-opencode"]
