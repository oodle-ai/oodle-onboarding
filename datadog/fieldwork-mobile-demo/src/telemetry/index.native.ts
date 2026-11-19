import {
  CoreConfiguration,
  DdSdkReactNative,
  DdRum,
  DdLogs,
  ErrorSource,
  FeatureOperationFailure,
  PropagatorType,
  RumActionType,
  SdkVerbosity,
  TrackingConsent,
  VitalsUpdateFrequency,
} from "@datadog/mobile-react-native";
import {
  SessionReplay,
  ImagePrivacyLevel,
  TextAndInputPrivacyLevel,
  TouchPrivacyLevel,
} from "@datadog/mobile-react-native-session-replay";
import { apiUrl, ddConfig } from "../config";
import { Telemetry } from "./types";

let enabled = false;
let replayEnabled = false;
let replayWanted = true;
let consentGranted = true;
let currentView: string | undefined;
let transitions = Promise.resolve();
let viewReady = false;
let displayed = false;
const quietly = (promise: Promise<unknown>) => {
  void promise.catch(() => undefined);
};

export const telemetry: Telemetry = {
  async initialize(consent) {
    consentGranted = consent;
    if (!ddConfig.enabled || !ddConfig.applicationId || !ddConfig.clientToken)
      return "Not configured";
    const config = new CoreConfiguration(
      ddConfig.clientToken,
      ddConfig.env,
      consent ? TrackingConsent.GRANTED : TrackingConsent.NOT_GRANTED,
      {
        site: ddConfig.site,
        service: "fieldwork-one-mobile",
        version: "1.0.0",
        verbosity: SdkVerbosity.WARN,
        rumConfiguration: {
          applicationId: ddConfig.applicationId,
          trackInteractions: true,
          useAccessibilityLabel: true,
          trackResources: true,
          trackFetchResources: true,
          trackErrors: true,
          sessionSampleRate: ddConfig.sessionRate,
          resourceTraceSampleRate: ddConfig.traceRate,
          firstPartyHosts: [
            {
              match: new URL(apiUrl).hostname,
              propagatorTypes: [
                PropagatorType.DATADOG,
                PropagatorType.TRACECONTEXT,
              ],
            },
          ],
          nativeCrashReportEnabled: true,
          nativeViewTracking: false,
          nativeIosResourceTracking: false,
          trackNonFatalAnrs: true,
          trackWatchdogTerminations: true,
          trackMemoryWarnings: true,
          trackFrustrations: true,
          longTaskThresholdMs: 200,
          nativeLongTaskThresholdMs: 200,
          vitalsUpdateFrequency: VitalsUpdateFrequency.AVERAGE,
        },
        logsConfiguration: {},
        traceConfiguration: {},
      },
    );
    await DdSdkReactNative.initialize(config);
    enabled = true;
    await DdSdkReactNative.addAttributes({
      "demo.name": "fieldwork-one",
      "data.synthetic": true,
    });
    await DdSdkReactNative.setAccountInfo({
      id: "demo-harbor",
      name: "Harbor Environmental · Demo",
    });
    await SessionReplay.enable({
      replaySampleRate: ddConfig.replayRate,
      textAndInputPrivacyLevel: TextAndInputPrivacyLevel.MASK_ALL_INPUTS,
      imagePrivacyLevel: ImagePrivacyLevel.MASK_ALL,
      touchPrivacyLevel: TouchPrivacyLevel.SHOW,
      startRecordingImmediately: consent,
    });
    replayEnabled = true;
    return consent ? "Native RUM + Replay enabled" : "Collection paused";
  },
  view(key, name) {
    if (!enabled || currentView === key) return;
    const previous = currentView;
    currentView = key;
    viewReady = false;
    // Serialize view changes so fast navigation cannot stop the new view.
    transitions = transitions
      .then(async () => {
        if (previous) await DdRum.stopView(previous);
        await DdRum.startView(key, name);
        await DdRum.addFeatureFlagEvaluation("unified_workspace", true);
      })
      .catch(() => undefined);
  },
  action(name, attributes = {}) {
    if (enabled)
      quietly(DdRum.addAction(RumActionType.CUSTOM, name, attributes));
  },
  error(error, attributes = {}) {
    if (!enabled) return;
    const value = error instanceof Error ? error : new Error(String(error));
    quietly(
      DdRum.addError(
        value.message,
        ErrorSource.CUSTOM,
        value.stack || "",
        attributes,
      ),
    );
    quietly(DdLogs.error(value.message, attributes));
  },
  async user(user) {
    if (!enabled) return;
    await DdRum.stopSession();
    currentView = undefined;
    if (user)
      await DdSdkReactNative.setUserInfo({
        id: user.id,
        name: user.name,
        extraInfo: { "business.role": user.role },
      });
    else await DdSdkReactNative.clearUserInfo();
  },
  async consent(granted) {
    consentGranted = granted;
    if (!enabled) return;
    await DdSdkReactNative.setTrackingConsent(
      granted ? TrackingConsent.GRANTED : TrackingConsent.NOT_GRANTED,
    );
    if (replayEnabled)
      await (granted && replayWanted
        ? SessionReplay.startRecording()
        : SessionReplay.stopRecording());
  },
  async replay(record) {
    replayWanted = record;
    if (replayEnabled)
      await (record && consentGranted
        ? SessionReplay.startRecording()
        : SessionReplay.stopRecording());
  },
  ready() {
    if (enabled && currentView && !viewReady) {
      viewReady = true;
      quietly(
        transitions.then(async () => {
          await DdRum.addTiming("content_ready");
          await DdRum.addViewLoadingTime(false);
          if (!displayed) {
            displayed = true;
            await DdRum.reportAppFullyDisplayed();
          }
        }),
      );
    }
  },
  async sessionId() {
    return enabled ? DdRum.getCurrentSessionId() : undefined;
  },
  async operation(name, key, action) {
    if (enabled)
      await DdRum.startFeatureOperation(name, key, {}).catch(() => undefined);
    try {
      const result = await action();
      if (enabled) quietly(DdRum.succeedFeatureOperation(name, key, {}));
      return result;
    } catch (error) {
      if (enabled)
        quietly(
          DdRum.failFeatureOperation(
            name,
            key,
            FeatureOperationFailure.ERROR,
            {},
          ),
        );
      throw error;
    }
  },
};
