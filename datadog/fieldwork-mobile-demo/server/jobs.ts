import { tracer } from "./telemetry";
import { processEvent } from "./domain";
import { Store } from "./store";

export async function runJobs(store: Store) {
  const pending = (await store.read()).events.filter(
    (event) => !event.processedAt,
  );
  for (const event of pending) {
    const parent = event.traceContext
      ? tracer.extract("text_map", event.traceContext)
      : null;
    await tracer.trace(
      "jobs.invoice.create",
      {
        childOf: parent ?? undefined,
        tags: { "order.id": event.orderId, "event.id": event.id },
      },
      () => store.transaction((state) => processEvent(state, event.id)),
    );
  }
  return pending.length;
}

export function startJobs(store: Store, onError: (error: unknown) => void) {
  let busy = false;
  const timer = setInterval(async () => {
    if (busy) return;
    busy = true;
    try {
      await runJobs(store);
    } catch (error) {
      onError(error);
    } finally {
      busy = false;
    }
  }, 2000);
  timer.unref();
  return () => clearInterval(timer);
}
