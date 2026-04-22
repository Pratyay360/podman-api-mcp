FROM oven/bun:1 AS base
WORKDIR /app
COPY . .

EXPOSE 3000

RUN bun install

CMD ["bun", "./src/index.ts"]
