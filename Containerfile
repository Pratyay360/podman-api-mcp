FROM ghcr.io/astral/bun:latest

WORKDIR /app
COPY . .

EXPOSE 3000

RUN bun install

CMD ["bun", "./src/index.ts"]
