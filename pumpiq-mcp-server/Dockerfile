FROM node:22-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci --production=false

COPY tsconfig.json ./
COPY src/ ./src/
RUN npm run build

RUN npm prune --production

# Install mcpo (Python-based MCP-to-OpenAPI bridge)
RUN apk add --no-cache python3 py3-pip && \
    pip3 install --break-system-packages mcpo

EXPOSE 8001

# mcpo wraps the stdio MCP server into an HTTP endpoint
CMD ["mcpo", "--port", "8001", "--host", "0.0.0.0", "--", "node", "/app/dist/index.js"]
