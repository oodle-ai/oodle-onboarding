# Oodle RUM and Session Replay

The app can send its native RUM and replay to Oodle instead of Datadog.
The provider is a build setting; one build sends to one provider. The
backend tracing in [DATADOG.md](DATADOG.md) is not affected by it.

## Native client configuration

In Oodle, open **Settings > API Keys** and create a key with the RUM
role. A RUM key can only write RUM data, so it is safe in the compiled
app. Copy your instance ID, the key, and the RUM collector URL from the
**Real User Monitoring** integration card into `.env`:

```dotenv
EXPO_PUBLIC_TELEMETRY_PROVIDER=oodle
EXPO_PUBLIC_OODLE_INSTANCE_ID=YOUR_INSTANCE_ID
EXPO_PUBLIC_OODLE_RUM_API_KEY=YOUR_RUM_API_KEY
EXPO_PUBLIC_OODLE_RUM_ENDPOINT=https://YOUR_COLLECTOR_DOMAIN
EXPO_PUBLIC_OODLE_ENV=demo
EXPO_PUBLIC_OODLE_SESSION_SAMPLE_RATE=100
EXPO_PUBLIC_OODLE_REPLAY_SAMPLE_RATE=100
EXPO_PUBLIC_OODLE_TRACE_SAMPLE_RATE=100
```

Rebuild and reinstall after changing these values
(`npm run build:android` or `npm run build:ios`). The Android helper
always creates a new JavaScript bundle, so a changed value is included.

The adapter is `src/telemetry/oodle.native.ts`. It uses the
`@oodle-ai/mobile-sdk-reactnative` package and the same `Telemetry`
interface as the Datadog adapter, so no screen changes. `OodleProvider`
wraps the app root and records taps.

## Native events and privacy

| Signal      | Sample behavior                                                                    |
| ----------- | ---------------------------------------------------------------------------------- |
| Views       | The named screens, with time on screen, load time and cold start time              |
| Actions     | Taps named by accessibility labels, rage taps, and the explicit workflow events    |
| Resources   | Fetch requests and their failures; trace headers only for the configured API host  |
| Errors      | JavaScript errors, handled demo errors, native crashes, ANRs and app hangs         |
| Performance | JS long tasks, refresh rate, slow and frozen frames, memory and CPU per screen     |
| Operations  | Workflow operations as custom events with status and duration                      |
| Context     | Synthetic user, role, demo account tags, and the `unified_workspace` feature flag  |
| Replay      | Wireframe replay of native screens with masked inputs, image placeholders, touches |

The API host gets W3C `traceparent` and Datadog trace headers, so the
backend traces in this sample link to the RUM resource events.

Open **More > Demo & observability** to pause collection or replay.
With the Oodle values missing from the environment, the controls do not
start the SDK.

## Verify delivery

1. Install a Release build on a phone or an emulator.
2. Allow telemetry. Sign in as Ava and visit Home, Shift, Schedule and Order.
3. Open the demo settings. Run a healthy, a slow and a failed request, and a handled JavaScript error.
4. Get the RUM session ID and search for it in the Oodle RUM Explorer.
5. Verify the named views, the tap actions, the request durations and the errors.
6. Open the session replay. Verify navigation, touches, masked inputs and image placeholders.
7. Pause consent and perform another action. Verify that collection stops.
