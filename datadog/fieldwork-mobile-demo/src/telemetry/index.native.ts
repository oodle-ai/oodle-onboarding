import { telemetryProvider } from "../config";
import { telemetry as datadog } from "./datadog.native";
import { telemetry as oodle } from "./oodle.native";
import { Telemetry } from "./types";

// Sends every call to both adapters. Oodle starts first, so Datadog's
// XHR wrapper sits outside Oodle's. Datadog then adds its trace headers
// before Oodle sees the request, and Oodle reuses that traceparent. In
// the other order, the request would carry two traceparent values.
const both: Telemetry = {
  async initialize(consent) {
    const oodleStatus = await oodle.initialize(consent);
    const datadogStatus = await datadog.initialize(consent);
    return `Oodle: ${oodleStatus} · Datadog: ${datadogStatus}`;
  },
  view(key, name) {
    oodle.view(key, name);
    datadog.view(key, name);
  },
  action(name, attributes) {
    oodle.action(name, attributes);
    datadog.action(name, attributes);
  },
  error(error, attributes) {
    oodle.error(error, attributes);
    datadog.error(error, attributes);
  },
  async user(user) {
    await Promise.all([oodle.user(user), datadog.user(user)]);
  },
  async consent(granted) {
    await Promise.all([oodle.consent(granted), datadog.consent(granted)]);
  },
  async replay(record) {
    await Promise.all([oodle.replay(record), datadog.replay(record)]);
  },
  ready() {
    oodle.ready();
    datadog.ready();
  },
  async sessionId() {
    const [o, d] = await Promise.all([oodle.sessionId(), datadog.sessionId()]);
    const ids = [o && `Oodle ${o}`, d && `Datadog ${d}`].filter(Boolean);
    return ids.length ? ids.join(" · ") : undefined;
  },
  operation(name, key, action) {
    return oodle.operation(name, key, () =>
      datadog.operation(name, key, action),
    );
  },
};

const adapters = {
  datadog: { name: "Datadog RUM + Session Replay", telemetry: datadog },
  oodle: { name: "Oodle RUM + Session Replay", telemetry: oodle },
  both: { name: "Datadog + Oodle RUM + Session Replay", telemetry: both },
};
export const telemetryName = adapters[telemetryProvider].name;
export const telemetry = adapters[telemetryProvider].telemetry;
