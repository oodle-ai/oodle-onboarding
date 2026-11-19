# Sample capabilities and boundaries

Fieldwork One is an observability teaching workload. Its generic service tasks exist to exercise mobile RUM, Session Replay, and backend traces. Its UI, identities, fixture image, business records, API routes, and service names are synthetic.

The sample is not intended to run a field-service business or replace commercial operations software. It makes no feature-parity or migration claims. Do not use it for real customer records, payments, or fleet operations.

## What the sample does not provide

| Area                  | Limit                                                                                            |
| --------------------- | ------------------------------------------------------------------------------------------------ |
| Identity              | Fixed demo profiles and known codes; no production authentication or tenant provisioning         |
| Business integrations | No payment processor, SMS provider, telephone integration, accounting export, or payroll system  |
| Fleet operations      | No route optimizer, live vehicle tracking, or complete container movement ledger                 |
| Data operations       | One workspace in a JSONB row; no production media storage or retention system                    |
| Mobile release        | No supplied signed app binaries; physical-device checks and live Datadog delivery remain pending |

The connected journeys below are test scenarios for telemetry. They do not establish suitability for business use.

## Connected journeys

| Journey                   | Entry                    | Result                                                                                    |
| ------------------------- | ------------------------ | ----------------------------------------------------------------------------------------- |
| Start a driver day        | Home → Start my day      | A safe inspection permits clock-in; a defect sends the truck to maintenance               |
| Deliver a container       | Schedule → Delivery      | Confirm a container, add a delivered photo, complete the job, and create an invoice       |
| Collect a container       | Schedule → Pickup        | Add a removed photo and a disposal ticket before completion                               |
| Swap or live load         | New order → Service type | Required evidence changes with the job type; disposal is required                         |
| Resolve a blocked job     | Job → Report issue       | Dispatch can return the job to the schedule                                               |
| Plan a route              | Dispatch                 | Assign an order at the first or last route position; move it between routes               |
| Coordinate the crew       | Comms                    | Persistent dispatch, huddle, and customer conversations                                   |
| Receive payment           | Invoices                 | Partial and full demo payments update the balance and payment history                     |
| Work without a connection | Pending actions          | Store actions in order; retry with stable request IDs; retain rejected actions for review |
| Review equipment          | Fleet & shop             | Track readiness, complete maintenance tasks, and view container inventory                 |
| Observe a session         | Demo & observability     | Exercise instrumented requests, failures, consent, and replay controls                    |

## Authorization and data

Driver profiles can read their own route, orders, shift history, inspections, and related customer records. Office profiles can dispatch, update customer notes, review evidence, record demo payments, and manage maintenance. The API enforces these rules independently of screen visibility.

The demo sign-in deliberately uses known profiles and codes. Its signed sessions prevent accidental profile spoofing in API requests, but the sign-in is not production authentication. There is no external identity provider or tenant provisioning.

The PostgreSQL sample stores the workspace in one JSONB row. Transactions serialize changes and make request-ID deduplication atomic. The separate worker records invoice creation and event completion in the same transaction. The file-store mode has the same domain rules, but requires one process.

## Deliberate simplifications

- The route graphic is an illustration. Site directions open an external maps app. There is no route optimizer or continuous GPS feed.
- The camera and photo library work on supported devices. Evidence is stored as bounded JPEG data in the sample state. There is no object-storage service or production media-retention policy.
- One container ID is confirmed per order. A swap demonstrates the workflow and evidence requirements, but does not maintain a two-container movement ledger.
- The recipient field records a name. It is not a drawn or legally verified signature.
- Messages use the sample API. Call outcomes, SMS sign-in, and payment methods are simulations. No calls, SMS, or payments are sent to external providers.
- The device can show a local notification. Native push-token registration is available when APNs or FCM is configured and enabled. The sample has no remote push sender.
- The API snapshot refreshes when the app becomes active, when an action completes, when the user refreshes, and every ten seconds while active. It does not use a live socket.
- The offline queue preserves actions but does not project their effects into a second local database. The screen displays the last confirmed server state until synchronization succeeds.
- The background worker uses a durable database outbox. It does not require a hosted workflow platform.
- The shop board covers vehicle maintenance. It does not integrate purchasing, parts inventory, payroll, taxes, or accounting exports.

These boundaries keep the app independently runnable. Each workflow generates useful RUM actions, resource requests, traces, or replay activity without requiring a customer's infrastructure.
