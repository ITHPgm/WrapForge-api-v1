# Production-readiness status and acceptance test plan

## Current foundation status

| Area | Included | Production verification still required |
|---|---|---|
| REST API | FastAPI, JSON request validation, auth, CORS, rate limits | Load test, penetration test, key lifecycle, proxy-level body caps |
| Multi-tenancy | Owner-scoped API keys, build rows, status/log/artifact checks | Account integration and concurrent isolation test |
| Domain proof | DNS TXT challenge and confirm | DNS edge cases, wildcard/subdomain policy, registrar propagation, ownership transfer/revoke |
| Queue | Redis + RQ, separate Android/iOS queues | Retry policy, dead-letter handling, cancellation, stuck-job reaper, queue monitoring |
| Android | Kotlin WebView template, Gradle APK/AAB tasks, generated signing key, `apksigner`/`jarsigner` output verification | Actual SDK compile, signature verification on target infrastructure, emulator + physical device test, Play Console upload test |
| iOS | Swift/WKWebView, XcodeGen project, IPA export flow and `codesign` validation | Mac worker setup, signing automation, TestFlight install, device tests, App Store Connect validation |
| Artifacts | Private local volume and S3-compatible option, SHA-256 | Backup/retention, malware scanning, signed URL lifecycle, restore tests |
| Frontend | Existing WrapForge dashboard should call the API | End-to-end integration and accessibility/responsive tests |
| Payments | Not part of this engine package | Keep in the existing PHP payment facade; verify server-side and idempotently |

## Verification to run on a provisioned Linux host

```bash
python -m pip install -r requirements.txt
python -m compileall engine tests alembic
python -m unittest discover -s tests -v
alembic upgrade head
# Bring up Postgres + Redis and configure .env first.
docker compose config
docker compose up --build -d
curl http://localhost:8000/health
```

Then run at least:

1. Create an API key for test owner A and another for owner B.
2. Verify a real test domain using its DNS TXT challenge.
3. Submit a full Android APK request and confirm `202` plus unique build ID.
4. Re-submit with the same `Idempotency-Key` and confirm it does not enqueue a duplicate.
5. Stream SSE events and confirm status/logs are persisted if the client disconnects.
6. Verify APK signature with `apksigner verify --verbose --print-certs app.apk`.
7. Verify AAB signature with `jarsigner -verify -verbose -certs app.aab` and inspect with `bundletool validate`.
8. Install the APK on physical Android 10, 13, 15, and 16 devices; test back navigation, HTTPS redirects, downloads, file selection, zoom, rotation, splash/loading, offline error, and screenshot policy.
9. Try owner B against owner A's build and artifact IDs; all reads and downloads must return 404.
10. Test malformed app IDs, non-HTTPS URLs, unverified hosts, DNS private IP answers, oversized requests, duplicate formats, and unsupported file formats.
11. Kill Redis while enqueuing and confirm the build is marked failed/visible rather than silently lost.
12. Kill a worker mid-build and test queue recovery without duplicate signing/artifacts.
13. Run load tests for API requests and sustained worker load; measure RAM, CPU, disk and build time.
14. Restore database, artifact storage, signing volume, and master key from backups in a clean environment.

## Verification to run on a macOS host

1. Install a supported Xcode release and Xcode Command Line Tools.
2. Install XcodeGen (`brew install xcodegen`).
3. Authenticate Xcode with the intended Apple Developer team.
4. Configure signing and provisioning. Confirm the correct distribution method for the target customer and release channel.
5. Start `scripts/start-ios-worker-macos.sh` with the shared DB/Redis/S3 configuration.
6. Request an IPA. Verify the `xcodebuild archive` and `-exportArchive` stages.
7. Inspect the IPA signature, bundle ID, entitlements, Info.plist, icon, supported orientations and WKWebView security settings.
8. Install through TestFlight or the matching allowed distribution channel and test on real iPhones/iPads.
9. Test upload fields, in-app Safari, external URL schemes, file downloads, navigation, lifecycle, no-network behaviour and screenshot warning.
10. Confirm that one tenant cannot use another tenant's certificate or provisioning profile.

## Known gaps not to advertise as implemented

- Per-customer Apple certificate/provisioning-profile upload, encrypted vault, expiry monitoring, and revocation lifecycle.
- Push notifications/FCM/APNs, camera, microphone, geolocation, biometrics, QR scanner, app links/universal links, AdMob and analytics native plugins.
- Full app-store policy scan or guarantee of store approval.
- Native Flutter and React Native generation. These need separate adapters and templates, not a boolean frontend switch.
- Website ZIP upload/source bundle compilation; this engine builds URL-based wrappers. A PHP/Node site remains hosted and is loaded in the WebView.
- Website offline mirroring/PWA service-worker support across all websites. A remote server-side web app still needs an active network unless its own offline implementation exists.
- Dedicated app versioning, signing-key upload/export/recovery workflow, team/org roles, admin dashboard, support tickets, email notifications and billing plan enforcement.
- Exact real-time compiler percentage and line-by-line compiler-log streaming; current progress values are coarse pipeline milestones and persisted events report build-stage status only.

Do not accept paying production users until the acceptance tests for the target platform are passing in the actual deployment environment.
