# Validation record

Validated on 20 November 2026 with Node 22.20.0. All test data was synthetic. No customer credentials or production services were used.

## Completed checks

| Check                                   | Result                                                                                                                         |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| TypeScript, mobile and server           | Passed                                                                                                                         |
| API behavior tests                      | Eight tests passed                                                                                                             |
| Android QR installer                    | Four HTTP tests passed with a synthetic APK fixture; browser download and QR decoding passed                                   |
| Android Java selection                  | Two tests passed: Java 27 rejection and Java 25 selection through `.env.local`                                                 |
| Android native release build            | Passed locally with Android Studio Java 25; APK signature verified                                                             |
| Browser production bundle               | Passed                                                                                                                         |
| iOS and Android JavaScript bundles      | Passed; native Hermes bundles generated                                                                                        |
| Expo native project generation          | Passed with symbol upload disabled                                                                                             |
| Local HTTP and HTTPS transport settings | Checked in the generated Android manifest and iOS plist                                                                        |
| Expo dependency and project checks      | 19 of 20 passed; the remaining check requires local CocoaPods                                                                  |
| Expo fingerprint generation             | Passed with the patched matcher dependency                                                                                     |
| Dependency audit                        | No reported vulnerabilities after the scoped matcher update                                                                    |
| Docker build and service startup        | API, PostgreSQL, Redis, and worker started; API and data services were healthy                                                 |
| Full service test                       | Passed: duplicate requests, job completion, separate-worker invoice creation, duplicate payment prevention, and cached reports |
| Browser layout                          | Inspected at 390 × 844 and 1280 × 900                                                                                          |
| Public-content review                   | Checked source, docs, config, identifiers, and assets for customer-specific references                                         |

Repository hooks also passed: whitespace, file endings, YAML, file size, merge markers, and private-key detection.

The local device helper passed checks with temporary settings and local command stubs. These checks covered settings preservation, credential propagation, APK output, Xcode preparation, local build arguments, missing tools, and API failures. They do not compile or sign a native app. Native project generation also confirmed that the default local-notification configuration omits the APNs entitlement.

The API tests cover delivery, pickup, swap, and live-load evidence requirements. They also cover driver permissions, invalid transitions, failed-transaction rollback, persisted state, maintenance, shift rules, invoice and payment deduplication, and phone-code reuse.

The browser walkthrough covered driver sign-in, inspection, clock-in, job start, container confirmation, photo upload, completion, background billing, office payment, new-order creation, and assignment to the first route position. An offline message remained in the queue after a browser reload with API requests blocked. It synchronized after the connection returned.

## Checks that need a device or credentials

- The Android APK was built and its signature was verified. Installation and runtime behavior still need a device check. An iOS binary has not been built. Local build and direct-install steps are in [INSTALL.md](INSTALL.md).
- Camera, photo-library, location, notification permission prompts, native SQLite photo queues, and background transitions need physical-device checks.
- Datadog credentials were not supplied. Native RUM ingestion, native replay rendering, RUM-to-APM links, correlated log delivery, and symbol upload remain unverified in Datadog.
- The browser preview does not prove native replay behavior. Use the device verification sequence in [DATADOG.md](DATADOG.md).
- The CI workflow is included. It was not run on GitHub during this session.

The sample includes simulated phone verification, calls, and payments. Remote push delivery, a live map feed, a route optimizer, and a full container movement ledger are outside its scope. See [CAPABILITIES.md](CAPABILITIES.md).
