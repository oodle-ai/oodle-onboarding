import "dotenv/config";
import tracer from "dd-trace";

process.env.DD_TRACE_ENABLED ??= "false";
tracer.init({
  service: process.env.DD_SERVICE || "fieldwork-demo-api",
  env: process.env.DD_ENV || "demo",
  version: "1.0.0",
  logInjection: true,
  runtimeMetrics: process.env.DD_TRACE_ENABLED === "true",
});
export { tracer };
