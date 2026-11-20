import { telemetryProvider } from "../config";
import { telemetry as datadog } from "./datadog.native";
import { telemetry as oodle } from "./oodle.native";

export const telemetryName =
  telemetryProvider === "oodle"
    ? "Oodle RUM + Session Replay"
    : "Datadog RUM + Session Replay";
export const telemetry = telemetryProvider === "oodle" ? oodle : datadog;
