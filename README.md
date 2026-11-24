<<<<<<< HEAD
# WrapForge Build Engine — production-oriented backend foundation

A queue-backed Web-to-App build service for generating **signed Android APK/AAB** packages and **iOS IPA** packages. The service accepts a complete build request, records an immutable build configuration, queues compilation, persists build events, and serves generated artifacts only to the owning API identity.

> **Release status:** This is a deployable engineering foundation, not a production-certified SaaS release. Android uses a real Gradle/Kotlin project template. IPA generation is implemented as a separate macOS/Xcode worker and requires an Apple Developer team with automatic signing configured. The supplied environment cannot run Gradle, Android SDK, Xcode, or Apple signing, so no claim is made that a package has compiled in this environment. Run the verification plan in `docs/PRODUCTION-READINESS.md` before taking live users or payments.

## What is included

- FastAPI REST API with POST/GET endpoints, API-key authentication, per-owner rate limiting, configurable CORS, request validation, and idempotency keys.
- DNS TXT ownership challenge before a website can be packaged.
- Redis + RQ queues. Android and iOS jobs are separate queues so they can be processed on different operating systems.
- SQLAlchemy persistence for builds, domain verification, events, and artifacts.
- Server-Sent Events (SSE) for persisted pipeline-stage progress; status and event-log polling endpoints are also available. Compiler output is not yet streamed line-by-line.
- Android Kotlin WebView shell built by Gradle against Android API 36, producing signed APK and/or AAB.
- Swift/WKWebView iOS shell and XcodeGen project specification for a macOS worker that exports a signed IPA.
- Isolated per-build workspace directories and owner-scoped artifact storage.
- Stable per-app Android upload signing key derived from a server master secret. Never lose or rotate that secret without a controlled key migration.
- Local Docker Compose stack and a separate macOS worker launcher.
- `curl` examples, setup instructions, feature limitations, and release-readiness checklist.

## Platform outputs

| Platform | Request format | Build toolchain | Result |
|---|---|---|---|
| Android | `apk` | JDK 17, Android SDK 36, Gradle 8.13 | Signed `.apk` for direct installation |
| Android | `aab` | JDK 17, Android SDK 36, Gradle 8.13 | Signed `.aab` for Google Play upload |
| iOS | `ipa` | macOS, Xcode, XcodeGen, Apple signing | Signed `.ipa` for permitted iOS distribution |

APK and AAB are Android package formats. iOS builds produce IPA; there is no generic `.iOS` package format. A successful build does not guarantee App Store or Play Store approval.

## Quick start (local Android worker)

1. Install Docker Engine and Docker Compose.
2. Copy `.env.example` to `.env`.
3. Generate unique secrets and fill every `REPLACE_...` value. Do not commit `.env`.
4. Make `API_KEYS` use the exact format `key-id:owner-id:secret`. Example: `dev:local-demo:YOUR_RANDOM_SECRET`.
5. Set a stable `SIGNING_MASTER_KEY` with at least 48 random characters. Back it up securely.
6. Start the stack:

   ```bash
   docker compose up --build -d
   docker compose logs -f api android-worker
   ```

7. Check the service:

   ```bash
   curl http://localhost:8000/health
   ```

The API container runs `alembic upgrade head` before starting. The API is bound to `127.0.0.1:8000` by default. Put it behind a TLS reverse proxy; do not expose the worker or Redis directly to the public internet.

## Environment configuration

See `.env.example` for every supported variable. The important values are:

- `DATABASE_URL`: PostgreSQL connection string.
- `REDIS_URL`: Redis connection string.
- `API_KEYS`: comma-separated `key-id:owner-id:secret` credentials. One owner ID represents one isolated tenant/account.
- `CORS_ORIGINS`: exact trusted frontend origins; do not use `*` with credentials.
- `ARTIFACT_ROOT`, `WORK_ROOT`, `CONFIG_SNAPSHOT_ROOT`, `SIGNING_ROOT`: private filesystem directories for local/self-hosted deployment. Each request is recorded in PostgreSQL and an immutable `request.json` snapshot under `<app-slug>/<tenant-hash>/<build-uuid>/`.
- `SIGNING_MASTER_KEY`: stable secret used to derive the same Android signing password for the same owner + application identifier.
- `S3_*`: optional S3-compatible storage. Enable this for distributed deployments where the API and worker do not share a filesystem.
- `IOS_TEAM_ID`: Apple Developer team ID used by the dedicated macOS worker.

For real production, use a secret manager/KMS, encrypted backups, object storage with private access, and a separate worker network. Do not put API keys, Android keystores, Apple certificates, provisioning profiles, or payment secrets in the frontend bundle.

## API authentication

Every protected route requires the `X-API-Key` header in `key-id.secret` form. Example:

```bash
export WRAPFORGE_API_KEY='dev.YOUR_RANDOM_SECRET'
export WRAPFORGE_API='https://builder.example.com/api/v1'
```

**Do not ship this service key in browser JavaScript.** For the existing WrapForge dashboard, the browser should authenticate to the PHP session-based API. The PHP API should call this engine server-to-server and pass the trusted tenant identity. This standalone key adapter is intended for curl, private integrations, and backend-to-backend calls.

## Domain ownership verification

Before a domain can be packaged, the owner must prove control of it.

```bash
curl -X POST "$WRAPFORGE_API/domains/challenges" \
  -H "X-API-Key: $WRAPFORGE_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"hostname":"example.com"}'
```

Create the returned TXT record at `_wrapforge.example.com` exactly as returned. Wait for DNS propagation, then verify:

```bash
curl -X POST "$WRAPFORGE_API/domains/verify" \
  -H "X-API-Key: $WRAPFORGE_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"hostname":"example.com"}'
```

The hostname in `website_url` must match a verified hostname for the API key's owner. DNS A/AAAA records must also resolve to public IP addresses again at build submission time. Domain ownership checks are not a guarantee that the website is safe; the build worker does not crawl or execute the website. The mobile app loads the specified HTTPS site at runtime.

## Create an Android build

```bash
curl -X POST "$WRAPFORGE_API/builds" \
  -H "X-API-Key: $WRAPFORGE_API_KEY" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: customer-order-2026-001' \
  -d '{
    "platform": "android",
    "app_name": "Example Portal",
    "package_id": "com.example.portal",
    "website_url": "https://example.com",
    "formats": ["apk", "aab"],
    "features": {
      "launcher_icon": true,
      "allow_screenshots": true,
      "show_loading_indicator": true,
      "allow_zoom": true,
      "orientation": "sensor",
      "downloads_enabled": true,
      "file_uploads_enabled": true,
      "external_links": "in_app_browser",
      "javascript_enabled": true,
      "primary_color": "#635BFF",
      "status_bar_color": "#101522",
      "navigation_bar_color": "#101522",
      "app_icon_png_base64": null
    }
  }'
```

The response is `202 Accepted` and contains a `build_id`, a status URL, an events URL, and an artifacts URL. The same idempotency key with a changed payload returns `409 Conflict`. It does not wait for Gradle/Xcode to finish. Progress currently reports persisted pipeline stages and milestone percentages; it does not yet stream every compiler output line. `app_icon_png_base64` is optional; supply a base64-encoded square PNG (64–4096 pixels per side, up to 2 MB) with `launcher_icon: true` to use a custom launcher icon. If omitted or `launcher_icon` is false, a neutral default icon is generated because installable applications need an icon asset.

## Create an iOS build

Use a separate request with `platform: "ios"` and `formats: ["ipa"]`:

```bash
curl -X POST "$WRAPFORGE_API/builds" \
  -H "X-API-Key: $WRAPFORGE_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "platform": "ios",
    "app_name": "Example Portal",
    "package_id": "com.example.portal",
    "website_url": "https://example.com",
    "formats": ["ipa"],
    "features": {
      "allow_screenshots": true,
      "show_loading_indicator": true,
      "allow_zoom": true,
      "orientation": "portrait",
      "downloads_enabled": true,
      "file_uploads_enabled": true,
      "external_links": "in_app_browser",
      "javascript_enabled": true
    }
  }'
```

The `ios-builds` queue must be consumed by a dedicated macOS machine. Run `scripts/start-ios-worker-macos.sh` on that machine after configuring reachable private `DATABASE_URL` and `REDIS_URL` values, the same object-storage bucket, and Apple Developer signing. Docker Compose service names such as `postgres` and `redis` are not resolvable from a separate Mac host; use a managed/private database and Redis endpoint reachable by both the API and Mac worker. In production, configure S3-compatible object storage so artifacts written by the Mac are visible to the API. Xcode must be authenticated for the selected team and allowed to manage provisioning profiles, or a manual profile must be installed and configured. The worker checks for Xcode and XcodeGen and verifies the exported IPA code signature before storing it.

For a SaaS with multiple customers, do not use one global Apple team for all customers. Add a credential-vault workflow for each customer’s App Store Connect API key, distribution certificate, and provisioning profile, encrypted at rest with KMS, and isolate each signing job. The current worker supports an operator-configured team as an initial macOS lane; per-customer credential upload/rotation/revocation is still a production gap.

## Monitor build progress

Poll the build status:

```bash
curl "$WRAPFORGE_API/builds/BUILD_ID" -H "X-API-Key: $WRAPFORGE_API_KEY"
```

Stream persisted build-stage events with curl:

```bash
curl -N "$WRAPFORGE_API/builds/BUILD_ID/events" \
  -H "X-API-Key: $WRAPFORGE_API_KEY"
```

Get saved logs or artifacts:

```bash
curl "$WRAPFORGE_API/builds/BUILD_ID/logs" -H "X-API-Key: $WRAPFORGE_API_KEY"
curl "$WRAPFORGE_API/builds/BUILD_ID/artifacts" -H "X-API-Key: $WRAPFORGE_API_KEY"
```

Download with the URL returned by the artifacts endpoint and the same authenticated header. The browser can use `fetch()` with the API key held by a trusted server-side session; native `EventSource` cannot attach arbitrary headers, so use `fetch()` streaming or status polling from browser clients.

## Artifact storage and requested URL shape

The physical artifact storage hierarchy is:

```text
ARTIFACT_ROOT/
  example-portal/
    BUILD_UUID/
      example-portal.apk
      example-portal.aab
```

S3 mode uses the same logical key: `example-portal/BUILD_UUID/example-portal.apk`. The artifact is **not** exposed as an unauthenticated static file. Downloads go through an ownership check, and S3 downloads use short-lived presigned URLs. This prevents another user from guessing `host.com/app-name/app-name.apk` and downloading somebody else’s build. If a public vanity URL is required, issue a signed, short-lived download token from the authenticated PHP facade and route it to the private artifact object.

## Deploying

### Render

Use Render for the HTTPS API service, PostgreSQL, Redis-compatible Key Value, and a Linux background worker. The Android worker needs JDK 17, Android SDK 36, Gradle, enough disk, and predictable CPU/RAM. Store APK/AAB/IPA artifacts in S3-compatible object storage because Render persistent disks are attached to a single service instance and cannot be shared by the API and worker. Keep the Android signing volume persistent; start with one Android worker until signing-key persistence is handled by a shared encrypted key store.

The iOS worker must run on a Mac with Xcode. Use a self-hosted Mac runner or a managed macOS CI provider, connected privately to the same Redis/database and object storage. Render's Linux worker is not an iOS build machine.

### Vercel

Vercel is suitable for a static/Next.js dashboard frontend, not for this Gradle/Xcode build engine. Mobile compilation is a long-running queued job that needs a dedicated worker, Android SDK/JDK, persistent signing material, and artifact storage. Keep the API and workers on Render or dedicated infrastructure; have the Vercel frontend call the API.

## More documentation

- `docs/ARCHITECTURE.md` — components and request lifecycle.
- `docs/API-REFERENCE.md` — endpoint schemas and HTTP contract.
- `docs/SECURITY.md` — tenant isolation, domain verification, signing, CORS, and worker hardening.
- `docs/PRODUCTION-READINESS.md` — mandatory test plan and known gaps.
- `docs/RESEARCH-NOTES.md` — comparative findings from the supplied GitHub repositories, REA, Hugging Face and similar builders.
- `VERIFICATION-REPORT.md` — checks run here and platform validations still outstanding.
- `examples/build-request.android.json` and `examples/build-request.ios.json` — request bodies.

## License and reuse

This engine package is original integration code for the WrapForge workstream. The supplied Android/iOS templates and scripts are intended for modification. Before merging code from WrapForge/WrapForge2 or any external repository, preserve its license and attribution notices and review each dependency's licence and security posture.
=======
# WrapForge-api-v1
This wrapforge api v1 
>>>>>>> d8beaf53d930f8174600eed3228851f570d5ac11
