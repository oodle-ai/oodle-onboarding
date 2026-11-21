import { ReactNode } from "react";

// The web preview has no native telemetry wrapper.
export function TelemetryProvider({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
