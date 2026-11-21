import { datadogRum } from "@datadog/browser-rum";
import { apiUrl, ddConfig } from "../config";
import { Telemetry } from "./types";

let enabled = false;
let replayWanted = true;
let consentGranted = true;
let currentView: string | undefined;
let viewReady = false;
const sites: Record<string, string> = {
  US1: "datadoghq.com",
  US3: "us3.datadoghq.com",
  US5: "us5.datadoghq.com",
  EU1: "datadoghq.eu",
  AP1: "ap1.datadoghq.com",
  AP2: "ap2.datadoghq.com",
  US1_FED: "ddog-gov.com",
};
export const telemetryName = "Datadog Browser RUM + Session Replay";
export const telemetry: Telemetry = {
  async initialize(consent) {
    consentGranted = consent;
    if (
      !ddConfig.enabled ||
      !ddConfig.webApplicationId ||
      !ddConfig.webClientToken
    )
      return "Web preview · telemetry not configured";
    datadogRum.init({
      applicationId: ddConfig.webApplicationId,
      clientToken: ddConfig.webClientToken,
      site: sites[ddConfig.site] || ddConfig.site,
      service: "fieldwork-one-web",
      env: ddConfig.env,
      version: "1.0.0",
      sessionSampleRate: ddConfig.sessionRate,
      sessionReplaySampleRate: ddConfig.replayRate,
      traceSampleRate: ddConfig.traceRate,
      trackViewsManually: true,
      trackUserInteractions: true,
      trackResources: true,
      trackLongTasks: true,
      defaultPrivacyLevel: "mask-user-input",
      trackingConsent: consent ? "granted" : "not-granted",
      allowedTracingUrls: [
        {
          match: (url: string) => url.startsWith(`${apiUrl}/`),
          propagatorTypes: ["datadog", "tracecontext"],
        },
      ],
    });
    datadogRum.setGlobalContextProperty("data.synthetic", true);
    if (consent) datadogRum.startSessionReplayRecording();
    enabled = true;
    return consent ? "Browser RUM + Replay enabled" : "Collection paused";
  },
  view(key, name) {
    if (enabled && key !== currentView) {
      currentView = key;
      viewReady = false;
      datadogRum.startView({ name });
      datadogRum.addFeatureFlagEvaluation("unified_workspace", true);
    }
  },
  action(name, attributes) {
    if (enabled) datadogRum.addAction(name, attributes);
  },
  error(error, attributes) {
    if (enabled) datadogRum.addError(error, attributes);
  },
  async user(user) {
    if (!enabled) return;
    datadogRum.stopSession();
    currentView = undefined;
    if (user)
      datadogRum.setUser({ id: user.id, name: user.name, role: user.role });
    else datadogRum.clearUser();
  },
  async consent(granted) {
    consentGranted = granted;
    if (!enabled) return;
    datadogRum.setTrackingConsent(granted ? "granted" : "not-granted");
    if (granted && replayWanted) datadogRum.startSessionReplayRecording();
    else datadogRum.stopSessionReplayRecording();
  },
  async replay(record) {
    replayWanted = record;
    if (enabled) {
      if (record && consentGranted) datadogRum.startSessionReplayRecording();
      else datadogRum.stopSessionReplayRecording();
    }
  },
  ready() {
    if (enabled && currentView && !viewReady) {
      viewReady = true;
      datadogRum.addTiming("content_ready");
    }
  },
  async sessionId() {
    return enabled ? datadogRum.getInternalContext()?.session_id : undefined;
  },
  async operation(name, key, action) {
    const started = Date.now();
    try {
      const result = await action();
      this.action(`${name}.success`, {
        operation_id: key,
        duration_ms: Date.now() - started,
      });
      return result;
    } catch (error) {
      this.error(error, { operation: name });
      throw error;
    }
  },
};
