FROM node:20-slim AS base

FROM base AS deps
RUN apt-get update && apt-get install -y --no-install-recommends python3 make g++ && rm -rf /var/lib/apt/lists/*
WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci --ignore-scripts && npm rebuild better-sqlite3

FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

ENV NEXT_TELEMETRY_DISABLED=1

RUN npm run build

FROM base AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV DATABASE_PATH=/data/db.sqlite

RUN groupadd -g 1001 nodejs && useradd -u 1001 -g nodejs nextjs

COPY --from=builder /app/public ./public

RUN mkdir .next && chown nextjs:nodejs .next
RUN mkdir -p /data && chown -R nextjs:nodejs /data

COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=deps --chown=nextjs:nodejs /app/node_modules/better-sqlite3 ./node_modules/better-sqlite3

USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]

