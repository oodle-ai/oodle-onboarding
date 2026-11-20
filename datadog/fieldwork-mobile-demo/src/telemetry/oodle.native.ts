import { OodleRum, OodleSessionReplay } from "@oodle-ai/mobile-sdk-reactnative";
import { apiUrl, oodleConfig } from "../config";
import { Telemetry } from "./types";

let enabled = false;
let replayWanted = true;
let consentGranted = true;
let currentView: string | undefined;
let viewReady = false;
let displayed = false;

export const telemetry: Telemetry = {
  async initialize(consent) {
    consentGranted = consent;
    if (!oodleConfig.instanceId || !oodleConfig.apiKey || !oodleConfig.endpoint)
      return "Not configured";
    const ok = OodleRum.init({
      instanceId: oodleConfig.instanceId,
      apiKey: oodleConfig.apiKey,
      endpoint: oodleConfig.endpoint,
      service: "fieldwork-one-mobile",
      env: oodleConfig.env,
      version: "1.0.0",
      trackingConsent: consent ? "granted" : "not-granted",
      sessionSampleRate: oodleConfig.sessionRate,
      allowedTracingUrls: [
        {
          match: new URL(apiUrl).hostname,
          propagators: ["tracecontext", "datadog"],
        },
      ],
      traceSampleRate: oodleConfig.traceRate,
      longTaskThresholdMs: 200,
      tags: {
        "demo.name": "fieldwork-one",
        "data.synthetic": true,
        "account.id": "demo-harbor",
        "account.name": "Harbor Environmental · Demo",
      },
      sessionReplay: {
        sampleRate: oodleConfig.replayRate,
        textAndInputPrivacy: "mask-all-inputs",
        imagePrivacy: "mask-all",
        touchPrivacy: "show",
        startRecordingImmediately: consent,
      },
    });
    if (!ok) return "Configuration rejected";
    enabled = true;
    return consent ? "Native RUM + Replay enabled" : "Collection paused";
  },
  view(key, name) {
    if (!enabled || currentView === key) return;
    currentView = key;
    viewReady = false;
    OodleRum.startView(key, name);
    OodleRum.addFeatureFlag("unified_workspace", true);
  },
  action(name, attributes = {}) {
    if (enabled) OodleRum.addAction(name, attributes);
  },
  error(error, attributes = {}) {
    if (enabled) OodleRum.addError(error, attributes);
  },
  async user(user) {
    if (!enabled) return;
    // A new profile starts a new session, so each person's session stays separate.
    OodleRum.stopSession();
    currentView = undefined;
    if (user)
      OodleRum.setUser({
        id: user.id,
        name: user.name,
        "business.role": user.role,
      });
    else OodleRum.clearUser();
  },
  async consent(granted) {
    consentGranted = granted;
    if (!enabled) return;
    OodleRum.setTrackingConsent(granted ? "granted" : "not-granted");
    if (granted && replayWanted) OodleSessionReplay.start();
    else OodleSessionReplay.stop();
  },
  async replay(record) {
    replayWanted = record;
    if (!enabled) return;
    if (record && consentGranted) OodleSessionReplay.start();
    else OodleSessionReplay.stop();
  },
  ready() {
    if (!enabled || !currentView || viewReady) return;
    viewReady = true;
    OodleRum.addTiming("content_ready");
    OodleRum.reportViewLoaded();
    if (!displayed) {
      displayed = true;
      OodleRum.reportAppFullyDisplayed();
    }
  },
  async sessionId() {
    return enabled ? OodleRum.getSessionId() || undefined : undefined;
  },
  async operation(name, key, action) {
    if (enabled) OodleRum.startOperation(name, key);
    try {
      const result = await action();
      if (enabled) OodleRum.succeedOperation(name, key);
      return result;
    } catch (error) {
      if (enabled) OodleRum.failOperation(name, key, "error");
      throw error;
    }
  },
};
