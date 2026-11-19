import "./telemetry";
import { createStore } from "./store";
import { startJobs } from "./jobs";
import { logger } from "./app";

if (!process.env.DATABASE_URL)
  throw new Error(
    "The separate worker requires DATABASE_URL. The local API includes its own worker.",
  );
const store = createStore();
const stopJobs = startJobs(store, (error) =>
  logger.error({ error: String(error) }, "Background job failed"),
);
const keepAlive = setInterval(() => undefined, 60000);
const stop = () => {
  stopJobs();
  clearInterval(keepAlive);
  void store.close().then(() => process.exit(0));
};
process.once("SIGTERM", stop);
process.once("SIGINT", stop);
logger.info("Fieldwork demo worker is ready");
