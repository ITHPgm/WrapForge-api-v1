# REST API reference

Base path: `/api/v1`

All protected endpoints require `X-API-Key: key-id.secret`. JSON requests use `Content-Type: application/json`.

## Health

`GET /health/live` — liveness check (no authentication). `GET /health/ready` and `/health` check database and Redis readiness.

## Domain ownership

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/domains/challenges` | Create/update the owner's TXT verification token |
| POST | `/domains/verify` | Resolve `_wrapforge.<hostname>` TXT and mark the hostname verified |

Challenge body:

```json
{"hostname":"example.com"}
```

Verification body:

```json
{"hostname":"example.com"}
```

## Build requests

`POST /builds` — creates one queued build and returns `202 Accepted`.

Android request:

```json
{
  "platform": "android",
  "app_name": "My Website",
  "package_id": "com.example.mywebsite",
  "website_url": "https://example.com",
  "formats": ["apk", "aab"],
  "features": {
    "launcher_icon": true,
    "allow_screenshots": true,
    "show_loading_indicator": true,
    "allow_zoom": true,
    "orientation": "portrait",
    "downloads_enabled": true,
    "file_uploads_enabled": true,
    "external_links": "in_app_browser",
    "javascript_enabled": true,
    "primary_color": "#635BFF",
    "status_bar_color": "#101522",
    "navigation_bar_color": "#101522",
    "app_icon_png_base64": null
  }
}
```

iOS request uses `"platform":"ios"` and `"formats":["ipa"]`. Do not request APK/AAB for iOS.

Headers:

- `Idempotency-Key`: optional client-generated key (max 160 characters). Repeating an identical request with the same key for the same owner returns the existing build instead of enqueuing a duplicate. Reusing the same key with a different payload returns `409 Conflict`.
- `X-API-Key`: required tenant credential.

Accepted response:

```json
{
  "success": true,
  "build_id": "<uuid>",
  "platform": "android",
  "status": "queued",
  "progress": 0,
  "status_url": "/api/v1/builds/<uuid>",
  "events_url": "/api/v1/builds/<uuid>/events",
  "artifacts_url": "/api/v1/builds/<uuid>/artifacts"
}
```

## Build lifecycle

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/builds/{build_id}` | Build status and artifact metadata |
| GET | `/builds/{build_id}/events` | SSE stream of durable build events |
| GET | `/builds/{build_id}/logs` | Full saved event/log history |
| GET | `/builds/{build_id}/artifacts` | List outputs and authenticated download URLs |
| GET | `/builds/{build_id}/artifacts/{artifact_id}/download` | Download/redirect to private artifact |

The SSE endpoint emits `event: build` records with fields `id`, `status`, `progress`, `level`, `message`, and `created_at`. It emits `event: done` when the build is terminal. Reconnect with `Last-Event-ID` or `?after=<event-id>`.

## Status values

`queued`, `preparing`, `signing`, `compiling`, `validating`, `completed`, `failed`, `cancelled`.

## Common HTTP responses

| Status | Meaning |
|---|---|
| 202 | Build accepted and queued |
| 201 | Domain verification challenge created |
| 401 | Missing or invalid API key |
| 403 | Website domain has not been verified for this owner |
| 404 | Build/artifact does not exist for this owner |
| 413 | Request body exceeds configured limit |
| 409 | Idempotency key reused with different request data |
| 422 | Invalid request or DNS challenge failure |
| 429 | Owner rate limit exceeded |
| 503 | Database/queue/artifact storage unavailable |
