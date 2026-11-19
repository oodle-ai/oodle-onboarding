# Datadog RUM, Session Replay, and APM

The sample runs without credentials. Configure a new demo application and its own client token when you are ready to send telemetry. No customer application IDs, tokens, endpoints, or service names are included.

## Native client configuration

In Datadog, create a **React Native** RUM application. Enable Session Replay for that application. Copy the application ID and client token into `.env`:

```dotenv
EXPO_PUBLIC_DD_ENABLED=true
EXPO_PUBLIC_DD_APPLICATION_ID=YOUR_REACT_NATIVE_APPLICATION_ID
EXPO_PUBLIC_DD_CLIENT_TOKEN=YOUR_CLIENT_TOKEN
EXPO_PUBLIC_DD_SITE=US1
EXPO_PUBLIC_DD_ENV=demo
EXPO_PUBLIC_DD_SESSION_SAMPLE_RATE=100
EXPO_PUBLIC_DD_REPLAY_SAMPLE_RATE=100
EXPO_PUBLIC_DD_TRACE_SAMPLE_RATE=100
```

Use the site that contains your Datadog organization: `US1`, `US3`, `US5`, `EU1`, `AP1`, or `AP2`. A client token is designed for client applications. A Datadog API key is not. Never put an API key in an `EXPO_PUBLIC_*` value.

For `us5.datadoghq.com`, set `EXPO_PUBLIC_DD_SITE=US5`. The native SDK requires a site code. A hostname can cause it to use US1 instead. The device build commands reject invalid site codes.

The pinned native core, Session Replay, and Babel plugin versions are the same. The app initializes the SDK before it restores the session. It tracks navigation with stable screen names and separate view keys. The app sets synthetic user and account IDs and starts a new RUM session when the demo profile changes.

The [Datadog React Native setup guide](https://docs.datadoghq.com/real_user_monitoring/application_monitoring/react_native/setup/) describes client configuration. The [Session Replay setup guide](https://docs.datadoghq.com/session_replay/setup_and_configuration/) describes the native replay integration.

The local build commands read `datadog/fieldwork-mobile-demo/.env` directly. No hosted environment-variable setup is needed. Rebuild and reinstall after changing these values. For a debug build, restart Metro.

The Android helper always creates a new JavaScript bundle. This includes environment changes that Gradle can otherwise miss. In Datadog, use **Past 15 minutes**, set **Is Active** to **All**, and remove duration and action filters when you check a new recording.

The client token is included in the compiled app. Backend API keys must not use the `EXPO_PUBLIC_*` prefix. The environment file is ignored by Git.

## Native events and privacy

| Signal      | Sample behavior                                                                            |
| ----------- | ------------------------------------------------------------------------------------------ |
| Views       | Welcome, Home, Schedule, Order, Dispatch, Comms, and the remaining named screens           |
| Actions     | Automatic taps with accessibility labels and explicit workflow events                      |
| Resources   | Fetch requests and their failures; trace headers only for the configured API host          |
| Errors      | JavaScript errors, handled demo errors, and native crash reporting                         |
| Performance | Long tasks, native long tasks, mobile vitals, content-ready timing, and app display timing |
| Operations  | Feature-operation start, success, and failure around online workflow mutations             |
| Context     | Synthetic user, role, demo account, and the `unified_workspace` feature flag               |
| Replay      | Native replay with input masking, image masking, and touch display                         |
| Logs        | Handled client errors through the native log SDK                                           |

The Babel plugin and Metro wrapper support React Native replay metadata. Native input text and evidence images are masked. The sample does not add phone numbers, messages, site notes, photo bytes, or recipient names as custom telemetry attributes. Business IDs can appear in traces and events. They are synthetic in this sample.

Open **More → Demo & observability** to pause collection or replay. Consent is stored on the device. Replay pause is a control for the current app run. With collection disabled in the environment, these controls do not start the SDK.

## Optional browser preview telemetry

Create a separate **Browser** RUM application. Keep its ID separate from the React Native application's ID.

```dotenv
EXPO_PUBLIC_DD_ENABLED=true
EXPO_PUBLIC_DD_WEB_APPLICATION_ID=YOUR_BROWSER_APPLICATION_ID
EXPO_PUBLIC_DD_WEB_CLIENT_TOKEN=YOUR_BROWSER_CLIENT_TOKEN
```

The web preview uses `@datadog/browser-rum`, service `fieldwork-one-web`, and `mask-user-input` privacy. It does not use the native SDK. A browser replay validates browser behavior; it does not validate native replay or native image masking. Use only synthetic evidence when you test browser replay.

## Backend traces and logs

Set these values in `.env`:

```dotenv
DD_TRACE_ENABLED=true
DD_API_KEY=YOUR_DATADOG_API_KEY
DD_SITE=datadoghq.com
DD_ENV=demo
```

Then start the Agent profile:

```sh
make up-observability
```

The API and worker send traces to `http://datadog:8126` on the Compose network. Their service names are `fieldwork-demo-api` and `fieldwork-demo-worker`. The Agent reads only containers matched by the sample's include rule. Container labels configure API and worker JSON log collection. The Docker socket is mounted read-only for this local integration.

The Node tracer loads before Express, PostgreSQL, Redis, and Pino. It adds request spans, database and cache spans, `workflow.*` spans, and `jobs.invoice.create` spans. The completion event stores trace context so the separate worker can continue the originating trace. The API permits both Datadog and W3C trace headers. The client restricts trace propagation to the configured API host.

Open the office Home screen to call the cached report endpoint. Complete a job to create a worker span. Use the diagnostics screen to create a slow request or a controlled server error. The server setting `ENABLE_DEMO_SCENARIOS` must be `true` for these fault scenarios.

For a local Node API with an external Agent, set `DD_TRACE_AGENT_URL` to that Agent's reachable HTTP address. The mobile client sends RUM and replay directly to Datadog; it does not send them through the API or Agent.

## Source maps and native symbols

Symbol upload is off by default. The Expo plugin can enable uploads when build credentials are ready:

```dotenv
DATADOG_UPLOAD_ENABLED=true
DATADOG_API_KEY=YOUR_BUILD_ONLY_API_KEY
DATADOG_SITE=datadoghq.com
```

`DATADOG_API_KEY` is the variable used by the symbol-upload tools. `DD_API_KEY` is used by the backend Agent. Both are server or build secrets; neither belongs in the client bundle.

Put these build-only values in the same ignored `.env` file before running `npm run build:android` or `npm run build:ios`. The helper passes them to the local build tools. Do not put API keys in app configuration or client variables.

The `expo-datadog` plugin adds iOS dSYM and JavaScript source-map uploads, Android JavaScript source-map uploads, and Android mapping-file upload support. Android mapping files are only produced when release minification is enabled. Configure that in the generated Android project or an Expo build-properties plugin before expecting a mapping-file upload.

The source-map service is `fieldwork-one-mobile`, which matches the native runtime service. Keep the version in `app.config.ts`, the runtime SDK configuration, and the backend configuration aligned when changing the sample version. Do not enable uploads for credential-free builds. See the [Expo Datadog plugin](https://github.com/DataDog/expo-datadog) for build-tool configuration.

## Verify delivery after credentials are available

1. Install a local development or Release build on a physical phone.
2. Allow telemetry in the demo settings. Sign in as Ava and visit Home, Shift, Schedule, and Order.
3. Run one inspection and job completion. Open Comms and send a synthetic message.
4. Open the demo settings. Run a healthy request, a slow request, a failed request, and a handled JavaScript error.
5. Get the RUM session ID. Find that session in the new Datadog application.
6. Verify named views, tap actions, resource durations, and error details.
7. Open the replay. Verify navigation, scrolling, touch display, masked inputs, and masked evidence images.
8. Open a traced API resource. Verify the API, database, and workflow spans. Complete a job and verify its worker span.
9. Check logs for matching trace and span IDs. Verify that note text and photo contents are absent.
10. Pause consent. Perform another action. Verify that collection stops. Restore consent and verify that a new session resumes.
11. Repeat on Android and iOS. Check a signed release build as well as a development build.

Credential-free checks cannot prove Datadog ingestion, billing settings, symbol matching, or native replay rendering. Record those results after the supplied credentials and signed builds are available.
