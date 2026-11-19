import express from "express";
import cors from "cors";
import { createExpressMiddleware } from "@trpc/server/adapters/express";
import { randomUUID } from "node:crypto";
import { z } from "zod";
import { createClient } from "redis";
import pino from "pino";
import { appRouter } from "./router";
import { issueToken, readToken } from "./auth";
import { Store } from "./store";

export const logger = pino({ level: process.env.LOG_LEVEL || "info" });
const profiles = [
  "driver-ava",
  "driver-leo",
  "dispatcher-sam",
  "admin-morgan",
] as const;
export function createApp(store: Store) {
  const app = express();
  const challenges = new Map<
    string,
    { userId: string; expires: number; attempts: number }
  >();
  const redis = process.env.REDIS_URL
    ? createClient({ url: process.env.REDIS_URL })
    : undefined;
  redis?.on("error", (error) =>
    logger.warn(
      { message: error.message },
      "Redis is unavailable. The API uses the database.",
    ),
  );
  void redis?.connect().catch(() => undefined);
  const allowed = (
    process.env.CORS_ORIGINS || "http://localhost:8081,http://127.0.0.1:8081"
  ).split(",");
  app.disable("x-powered-by");
  app.use(
    cors({
      origin: (origin, callback) =>
        callback(null, !origin || allowed.includes(origin)),
      allowedHeaders: [
        "Content-Type",
        "Authorization",
        "traceparent",
        "tracestate",
        "x-datadog-origin",
        "x-datadog-trace-id",
        "x-datadog-parent-id",
        "x-datadog-sampling-priority",
        "x-datadog-tags",
      ],
    }),
  );
  app.use(express.json({ limit: "4mb" }));
  app.use((req, res, next) => {
    const started = performance.now();
    res.on("finish", () =>
      logger.info(
        {
          method: req.method,
          path: req.path,
          status: res.statusCode,
          durationMs: Math.round(performance.now() - started),
        },
        "Request complete",
      ),
    );
    next();
  });
  app.get("/health", async (_req, res) => {
    try {
      await store.read();
      res.json({
        status: "ok",
        storage: process.env.DATABASE_URL ? "postgres" : "file",
        cache: redis?.isReady ? "redis" : "disabled",
        demo: true,
      });
    } catch {
      res.status(503).json({ status: "unavailable" });
    }
  });
  app.post("/api/auth/otp/phone", async (req, res) => {
    const parsed = z.object({ profile: z.enum(profiles) }).safeParse(req.body);
    if (!parsed.success) {
      res.status(400).json({ error: "Select a demo profile." });
      return;
    }
    for (const [id, c] of challenges)
      if (c.expires < Date.now()) challenges.delete(id);
    if (challenges.size > 1000) {
      res.status(429).json({ error: "Try again later." });
      return;
    }
    const challengeId = randomUUID();
    challenges.set(challengeId, {
      userId: parsed.data.profile,
      expires: Date.now() + 5 * 60 * 1000,
      attempts: 0,
    });
    res.json({ challengeId, demoCode: "123456", expiresIn: 300 });
  });
  app.post("/api/auth/otp/verify", async (req, res) => {
    const parsed = z
      .object({ challengeId: z.string(), code: z.string().max(20) })
      .safeParse(req.body);
    const challenge = parsed.success
      ? challenges.get(parsed.data.challengeId)
      : undefined;
    if (
      !parsed.success ||
      !challenge ||
      challenge.expires < Date.now() ||
      challenge.attempts >= 5
    ) {
      res
        .status(401)
        .json({ error: "The code expired. Request a new demo code." });
      return;
    }
    challenge.attempts += 1;
    if (parsed.data.code !== "123456") {
      res.status(401).json({ error: "Use the demo code 123456." });
      return;
    }
    challenges.delete(parsed.data.challengeId);
    const user = (await store.read()).users.find(
      (u) => u.id === challenge.userId,
    )!;
    res.json({ token: issueToken(user), user });
  });
  app.post("/api/auth/login", async (req, res) => {
    const parsed = z
      .object({ profile: z.enum(profiles), code: z.literal("demo") })
      .safeParse(req.body);
    if (!parsed.success) {
      res
        .status(401)
        .json({ error: "Select a demo profile and use the demo sign-in." });
      return;
    }
    const user = (await store.read()).users.find(
      (u) => u.id === parsed.data.profile,
    )!;
    res.json({ token: issueToken(user), user });
  });
  app.get("/api/report", async (req, res) => {
    const userId = readToken(
      req.headers.authorization?.replace(/^Bearer /, ""),
    );
    const state = await store.read();
    const user = state.users.find((u) => u.id === userId);
    if (!user || user.role === "driver") {
      res.status(403).json({ error: "An Office profile is required." });
      return;
    }
    const key = `fieldwork:report:${state.revision}`;
    const cached = redis?.isReady
      ? await redis.get(key).catch(() => null)
      : null;
    const result =
      cached ||
      JSON.stringify({
        orders: state.orders.length,
        completed: state.orders.filter((o) => o.status === "completed").length,
        revenueCents: state.payments.reduce((sum, p) => sum + p.amountCents, 0),
        outstandingCents: state.invoices.reduce(
          (sum, i) => sum + i.amountCents - i.paidCents,
          0,
        ),
      });
    if (!cached && redis?.isReady)
      await redis.set(key, result, { EX: 30 }).catch(() => undefined);
    res.type("json").send(result);
  });
  app.use(
    "/api/trpc",
    createExpressMiddleware({
      router: appRouter,
      createContext: async ({ req }) => {
        const userId = readToken(
          req.headers.authorization?.replace(/^Bearer /, ""),
        );
        return {
          store,
          user: userId
            ? (await store.read()).users.find((u) => u.id === userId)
            : undefined,
        };
      },
      onError: ({ error, path }) => {
        if (error.code === "INTERNAL_SERVER_ERROR")
          logger.error(
            { path, message: error.message },
            "API operation failed",
          );
      },
    }),
  );
  app.use(
    (
      error: unknown,
      _req: express.Request,
      res: express.Response,
      _next: express.NextFunction,
    ) => {
      logger.error(
        { error: error instanceof Error ? error.message : "Unknown error" },
        "Request failed",
      );
      res.status(400).json({ error: "The request could not be processed." });
    },
  );
  return {
    app,
    close: async () => {
      if (redis?.isOpen) await redis.quit();
      await store.close();
    },
  };
}
