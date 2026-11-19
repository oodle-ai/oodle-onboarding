import "./telemetry";
import { createStore } from "./store";
import { createApp, logger } from "./app";
import { startJobs } from "./jobs";

const store = createStore();
const { app, close } = createApp(store);
const stopJobs =
  process.env.RUN_WORKER === "false"
    ? () => undefined
    : startJobs(store, (error) =>
        logger.error({ error: String(error) }, "Background job failed"),
      );
const port = Number(process.env.PORT || 4310);
const server = app.listen(port, process.env.HOST || "127.0.0.1", () =>
  logger.info({ port }, "Fieldwork demo API is ready"),
);
const stop = () => {
  stopJobs();
  server.close(() => {
    void close().then(() => process.exit(0));
  });
};
process.once("SIGTERM", stop);
process.once("SIGINT", stop);
