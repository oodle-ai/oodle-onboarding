# Oodle RUM and Session Replay

The app can send its native RUM and replay to Oodle, either instead of
Datadog or alongside it. The provider is a build setting. The backend
traces go through the Datadog Agent; see
[Backend traces](#backend-traces) to send them to Oodle too.

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

## Send to Datadog and Oodle together

Set `EXPO_PUBLIC_TELEMETRY_PROVIDER=both` and fill in both the Datadog
values from [DATADOG.md](DATADOG.md) and the Oodle values above. Each
event is then sent once to each backend.

- Oodle starts before Datadog. Datadog adds its trace headers to the API
  request first, and Oodle reuses that `traceparent`. The RUM resource
  in both tools links to the same backend trace. Oodle sends its client
  span with Datadog's span ID, so the trace in Oodle also starts at the
  app.
- Datadog drops the Oodle SDK's uploads from its resources, so they do
  not appear as app requests.
- Each SDK keeps its own session. **Get current RUM session ID** shows
  both IDs.
- Two replay recorders run, so replay costs about twice the CPU, memory
  and upload traffic. The performance numbers in each tool include the
  other SDK's work. Use one provider when you compare performance.

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

## Backend traces

The SDK sends a client span for each traced API request. In Oodle APM,
the app is the `fieldwork-one-mobile` service, and each span is the
parent of the API spans of the same request. The API spans come from
`dd-trace` through the Datadog Agent.

In Oodle, open **Settings > API Keys** and create an ingestion key. The
Agent cannot use the RUM key. Copy the instance ID and the collector URL
from the **Datadog** integration card into `.env`. These are backend
values. Do not use the `EXPO_PUBLIC_` prefix:

```dotenv
OODLE_INSTANCE_ID=YOUR_INSTANCE_ID
OODLE_COLLECTOR_URL=https://YOUR_COLLECTOR_DOMAIN
OODLE_API_KEY=YOUR_INGESTION_API_KEY
```

Then start the stack with the Agent in one of two modes:

| Command              | Traces go to      | Needs                             |
| -------------------- | ----------------- | --------------------------------- |
| `make up-oodle`      | Datadog and Oodle | `DD_API_KEY` and the values above |
| `make up-oodle-only` | Oodle             | the values above                  |

Both modes set `DD_TRACE_ENABLED=true` for the API and the worker. In
`up-oodle-only`, the Oodle key replaces the Datadog key, the Agent
metrics go to Oodle, and the Agent does not collect container logs.
The Agent log then shows periodic 403 errors for Datadog products that
have no Oodle endpoint. Traces and metrics are not affected.

To verify, run a healthy request in **Demo & observability**. Open
Oodle APM and find the `fieldwork-one-mobile` service. Open a trace of a
request: the app's client span is the root, and the
`fieldwork-demo-api` spans, including its PostgreSQL queries, are below
it. The app's spans also have `session.id`, which links the trace to
the RUM session.

The app must send its requests to this stack. Set
`EXPO_PUBLIC_API_URL` to the address of the Compose API and rebuild the
app. A request made with `curl` and a copied `traceparent` does not
test the app: the trace then has no request from the app's network
stack.

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
