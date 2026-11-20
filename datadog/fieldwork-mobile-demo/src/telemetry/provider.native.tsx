import { OodleProvider } from "@oodle-ai/mobile-sdk-reactnative";
import { ReactNode } from "react";
import { telemetryProvider } from "../config";

// Oodle records taps from a root touch observer. Datadog's Babel plugin
// wraps the handlers instead, so it needs no wrapper.
export function TelemetryProvider({ children }: { children: ReactNode }) {
  return telemetryProvider === "oodle" ? (
    <OodleProvider>{children}</OodleProvider>
  ) : (
    <>{children}</>
  );
}
