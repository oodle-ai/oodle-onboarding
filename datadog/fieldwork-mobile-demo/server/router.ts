import { initTRPC, TRPCError } from "@trpc/server";
import { z } from "zod";
import { envelopeSchema, User } from "../src/shared/model";
import { DomainError, execute, snapshot } from "./domain";
import { Store } from "./store";
import { tracer } from "./telemetry";

export type Context = { store: Store; user?: User };
const t = initTRPC.context<Context>().create();
const protectedProcedure = t.procedure.use(({ ctx, next }) => {
  if (!ctx.user)
    throw new TRPCError({
      code: "UNAUTHORIZED",
      message: "Sign in again to continue.",
    });
  return next({ ctx: { ...ctx, user: ctx.user } });
});
export const appRouter = t.router({
  sync: t.router({
    snapshot: protectedProcedure.query(({ ctx }) =>
      ctx.store.read().then((state) => snapshot(state, ctx.user)),
    ),
  }),
  workflow: t.router({
    execute: protectedProcedure
      .input(envelopeSchema)
      .mutation(async ({ ctx, input }) => {
        try {
          return await tracer.trace(
            `workflow.${input.command.type}`,
            {
              tags: {
                "usr.id": ctx.user.id,
                "business.role": ctx.user.role,
                "request.id": input.requestId,
              },
            },
            async () => {
              const carrier: Record<string, string> = {};
              const span = tracer.scope().active();
              if (span) tracer.inject(span, "text_map", carrier);
              return ctx.store.transaction((state) =>
                execute(state, ctx.user, input, undefined, carrier),
              );
            },
          );
        } catch (error) {
          if (error instanceof DomainError)
            throw new TRPCError({ code: error.code, message: error.message });
          throw error;
        }
      }),
  }),
  diagnostics: t.router({
    probe: protectedProcedure
      .input(z.object({ scenario: z.enum(["healthy", "slow", "error"]) }))
      .query(async ({ input }) => {
        if (
          process.env.ENABLE_DEMO_SCENARIOS !== "true" &&
          input.scenario !== "healthy"
        )
          throw new TRPCError({
            code: "FORBIDDEN",
            message: "Demo scenarios are disabled on the server.",
          });
        if (input.scenario === "slow")
          await new Promise((resolve) => setTimeout(resolve, 1800));
        if (input.scenario === "error")
          throw new TRPCError({
            code: "INTERNAL_SERVER_ERROR",
            message: "Demo failure: the dispatch service is unavailable.",
          });
        return {
          ok: true,
          scenario: input.scenario,
          at: new Date().toISOString(),
        };
      }),
  }),
});
export type AppRouter = typeof appRouter;
