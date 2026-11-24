# Architecture and build lifecycle

## Logical topology

```text
Dashboard / CLI / Integration
        |
        | HTTPS POST /api/v1/builds
        v
FastAPI REST API ---- PostgreSQL (builds, tenants, events, domains, artifacts) + private request.json snapshots
        |  \
        |   +---- Redis rate limits + RQ queues
        |                 |
        |                 +---- android-builds ---- Linux Android worker
        |                 |                         JDK + SDK 36 + Gradle
        |                 |                         Kotlin WebView template
        |                 |
        |                 +---- ios-builds -------- macOS worker
        |                                           Xcode + XcodeGen + Swift/WKWebView
        |
        +---- GET status / SSE events / authenticated artifact download

Artifacts -> private S3-compatible object storage (recommended) or local private volume
Signing    -> persistent encrypted signing volume / KMS-backed credential vault
```

## Why the build endpoint returns 202

A mobile build is not an HTTP response-time operation. The API validates the complete request, checks domain ownership, creates the build row, writes the first event, queues a job, and returns `202 Accepted` with a stable build ID. The frontend then opens the status URL or streams events. Do not keep the original POST open while Gradle or Xcode runs; that makes proxy timeouts, worker restarts, and retries harder to manage.

## Single-submission and step-by-step modes

The engine's canonical API accepts a complete JSON request once. A multi-step wizard should keep its draft state in the dashboard (or persist a server-side project draft) and submit one complete request when the user presses **Build**. If API-driven steps are required, add `POST /build-drafts`, `PATCH /build-drafts/{id}`, and `POST /build-drafts/{id}/build`; the final route must call the same validated build service. Never start compilation while required fields are still missing.

## Tenant and build isolation

Each API key maps to one `owner_id`. The owner is attached server-side; clients cannot submit an owner ID in the build payload. Every build gets a UUID. The canonical values live in PostgreSQL; an immutable, private JSON manifest is also written under `<app-slug>/<tenant-hash>/<build-uuid>/request.json` for audit and recovery. Workspaces use a hash of the owner ID plus build UUID. Artifact keys use `{app-slug}/{build-uuid}/{app-slug}.{format}`. API reads and downloads always verify `(build_id, owner_id)` before returning data.

The friendly app folder is not the security boundary. The UUID and ownership check are. Do not expose the artifact directory through Nginx static file serving.

## Build engines

### Android

The Android template is a Kotlin `WebView` wrapper. Gradle receives validated app metadata and feature flags as command-line properties. Release tasks are `:app:assembleRelease` and `:app:bundleRelease`. The build worker creates/uses a stable per-owner + package signing keystore, verifies that the output is a ZIP-based package, calculates SHA-256, and moves the final file into private storage.

### iOS

The iOS template is Swift + `WKWebView`. XcodeGen creates an Xcode project from `templates/ios/project.yml`. The macOS worker archives the app and exports a signed IPA using Xcode. IPA production requires macOS, Xcode, signing certificates, a provisioning profile/team, and App Store Connect configuration appropriate to the intended distribution method.

### Why Flutter and React Native are not enabled as generic toggles

Flutter and React Native are full application runtimes with their own dependency resolution, generated project layout, native plugin ecosystem, and signing/build toolchains. A website URL alone is not enough to create a Flutter or React Native application with equivalent web-wrapper behaviour. The initial supported engine is the native WebView shell (Kotlin/Swift). Add Flutter/RN only as explicit adapters with maintained templates, plugin allowlists, tests, and separate worker images; do not show a frontend option that has no functioning builder behind it.

Capacitor is a strong optional future adapter where the website requires a plugin bridge and common cross-platform runtime. It can produce AAB/APK/IPA outputs, but iOS still needs Xcode/macOS. See the research notes and upstream docs.

## Real-time event transport

`BuildEvent` is the durable event log. The API streams rows as Server-Sent Events and also exposes `/logs` for polling/recovery. The frontend must retain the last event ID and reconnect using `Last-Event-ID` or `?after=...`. A connection is not the source of truth; PostgreSQL is. If an SSE connection drops, the client reconnects and receives missed events.

## Build stage semantics

The `progress` field is a coarse pipeline indicator, not an exact compiler percentage. Stages include queued, preparing, signing (Android), compiling, validating, completed, and failed. The worker currently persists pipeline-stage transitions and milestone messages; line-by-line Gradle/Xcode output capture is a follow-on implementation item. Do not fabricate a smooth 0–100 progress animation; show the stage and log messages, with the last numeric milestone clearly labelled as approximate.
