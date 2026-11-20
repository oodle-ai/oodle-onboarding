import { Platform } from "react-native";

export const apiUrl = (
  process.env.EXPO_PUBLIC_API_URL ||
  (Platform.OS === "android" ? "http://10.0.2.2:4310" : "http://localhost:4310")
).replace(/\/$/, "");
export const sampleRate = (value: string | undefined) => {
  const rate = Number(value ?? 100);
  return Number.isFinite(rate) ? Math.max(0, Math.min(100, rate)) : 100;
};
export const ddConfig = {
  enabled: process.env.EXPO_PUBLIC_DD_ENABLED === "true",
  applicationId: process.env.EXPO_PUBLIC_DD_APPLICATION_ID || "",
  clientToken: process.env.EXPO_PUBLIC_DD_CLIENT_TOKEN || "",
  webApplicationId: process.env.EXPO_PUBLIC_DD_WEB_APPLICATION_ID || "",
  webClientToken: process.env.EXPO_PUBLIC_DD_WEB_CLIENT_TOKEN || "",
  site: process.env.EXPO_PUBLIC_DD_SITE || "US1",
  env: process.env.EXPO_PUBLIC_DD_ENV || "demo",
  sessionRate: sampleRate(process.env.EXPO_PUBLIC_DD_SESSION_SAMPLE_RATE),
  replayRate: sampleRate(process.env.EXPO_PUBLIC_DD_REPLAY_SAMPLE_RATE),
  traceRate: sampleRate(process.env.EXPO_PUBLIC_DD_TRACE_SAMPLE_RATE),
};

// Selects the native telemetry adapter. Both SDKs are in the build; only
// the selected one is initialized.
export const telemetryProvider: "datadog" | "oodle" =
  process.env.EXPO_PUBLIC_TELEMETRY_PROVIDER === "oodle" ? "oodle" : "datadog";
export const oodleConfig = {
  instanceId: process.env.EXPO_PUBLIC_OODLE_INSTANCE_ID || "",
  apiKey: process.env.EXPO_PUBLIC_OODLE_RUM_API_KEY || "",
  endpoint: process.env.EXPO_PUBLIC_OODLE_RUM_ENDPOINT || "",
  env: process.env.EXPO_PUBLIC_OODLE_ENV || "demo",
  sessionRate: sampleRate(process.env.EXPO_PUBLIC_OODLE_SESSION_SAMPLE_RATE),
  replayRate: sampleRate(process.env.EXPO_PUBLIC_OODLE_REPLAY_SAMPLE_RATE),
  traceRate: sampleRate(process.env.EXPO_PUBLIC_OODLE_TRACE_SAMPLE_RATE),
};
