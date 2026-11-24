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

export async function pollJobs(store: Store) {
  // The poll span is the root of the read query and of each job that has
  // no request trace context, so each query shows which poll ran it.
  return tracer.trace("jobs.poll", { resource: "jobs.poll" }, async (span) => {
    const count = await runJobs(store);
    span?.setTag("jobs.pending", count);
    // An idle poll runs every 2 s. Drop its trace, because it holds only
    // the read query and hides the polls that did work.
    if (count === 0) span?.setTag("manual.drop", true);
    return count;
  });
}

export function startJobs(store: Store, onError: (error: unknown) => void) {
  let busy = false;
  const timer = setInterval(async () => {
    if (busy) return;
    busy = true;
    try {
      await pollJobs(store);
    } catch (error) {
      onError(error);
    } finally {
      busy = false;
    }
  }, 2000);
  timer.unref();
  return () => clearInterval(timer);
}
