import "dotenv/config";
import tracer from "dd-trace";

process.env.DD_TRACE_ENABLED ??= "false";
tracer.init({
  service: process.env.DD_SERVICE || "fieldwork-demo-api",
  env: process.env.DD_ENV || "demo",
  version: "1.0.0",
  logInjection: true,
  runtimeMetrics: process.env.DD_TRACE_ENABLED === "true",
  // Keep PostgreSQL and Redis spans in the service that calls them. Without
  // this, the tracer shows one service as three (`-postgres`, `-redis`).
  // peer.service keeps the database visible as a dependency.
  spanRemoveIntegrationFromService: true,
  spanComputePeerService: true,
});
// Connection-pool connects make dns.lookup and tcp.connect spans outside
// any request. They become one-span traces that hide the request traces.
tracer.use("dns", false);
tracer.use("net", false);
export { tracer };
