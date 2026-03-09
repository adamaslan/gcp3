FROM node:22-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci

COPY . .
# BUILD_STANDALONE=true enables next.config.ts output:"standalone" for Docker.
# Vercel builds do not pass this arg, so they get the default Vercel-compatible output.
ARG BUILD_STANDALONE=true
ENV BUILD_STANDALONE=$BUILD_STANDALONE
RUN npm run build

# Production image
FROM node:22-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV PORT=8080

COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 8080
CMD ["node", "server.js"]
