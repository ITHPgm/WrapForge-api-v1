# Research notes: existing Web-to-App engines and reusable patterns

This note records the upstream references reviewed while shaping this build engine. It is a design comparison, not a claim that all repositories were cloned, executed, or security-audited.

## Supplied repositories

### ITHPgm/WrapForge

Repository: https://github.com/ITHPgm/WrapForge

The README describes a mobile-first Expo dashboard and a seven-step app-builder workflow. Its build-history/preview flow is a useful UX reference, but its README states the Android build worker is not connected and the client uses local workspace state rather than a live compilation service. Preserve the builder's wizard and preview concepts, but do not treat the UI's build state as evidence of a produced APK/AAB. See the [project README](https://github.com/ITHPgm/WrapForge).

### ITHPgm/WrapForge2

Repository: https://github.com/ITHPgm/WrapForge2

This is the stronger backend reference. Its documented structure separates a PHP REST API, MySQL persistence, Node/Redis BullMQ orchestration, a Kotlin WebView template, a Gradle build worker, storage and Docker configuration. Its documented implementation includes CSRF/session controls, owner-scoped projects, DNS TXT site verification, queue-based builds and APK/AAB artifact handling. Its own implementation-status notes also identify missing end-to-end platform builds, worker egress isolation, advanced native capabilities and release certification. See the [repository README](https://github.com/ITHPgm/WrapForge2) and inspect its implementation-status document before merging any source.

**Architecture decision:** use WrapForge2 as the likely source-of-truth for the existing product because it already aligns with the PHP + Node + Redis + MySQL + Kotlin/Gradle stack. This separately packaged Python/FastAPI/RQ/PostgreSQL engine is a reference backend foundation, not a patch already merged into WrapForge2. Avoid operating two competing build queues and two sources of truth in one production system; pick one orchestration/API stack during integration.

## Reverse-engineering tool: REA

Repository: https://github.com/morluto/rea

REA is an agent/MCP-oriented reverse-engineering toolkit for analysing native binaries, Android packages, websites, JavaScript/Electron artifacts and other targets through available analysis providers. It is useful when source is unavailable, a compiled APK/AAB needs inspection, or an independent binary-level review is required. The supplied WrapForge repositories are source repositories, so normal source inspection, static analysis, tests and Git diffs are the correct first methods; decompiling readable TypeScript/PHP/Kotlin source is not useful. REA was researched but was not installed or executed in this environment. See the [REA repository](https://github.com/morluto/rea).

## Comparable GitHub projects

- [KCAPK](https://github.com/kc-apk/kcapk) demonstrates a CLI workflow for wrapping a website/static frontend in a native Android WebView application and producing Android release artifacts. Review its LGPL-3.0 licensing and dependencies before copying code.
- [html-to-apk](https://github.com/abuhoney/html-to-apk) is a useful API-oriented reference for accepting a build request, invoking Android packaging tools and exposing status/download routes. Treat it as a pipeline reference, not as a turnkey multi-tenant hosted build service.
- [Capacitor](https://github.com/ionic-team/capacitor) is the best candidate for a future cross-platform adapter when the wrapped website needs a managed plugin bridge and common Android/iOS runtime. It still uses native platform toolchains; iOS packaging still requires macOS/Xcode and Apple signing.

## Hugging Face

- [Wizcoderr/qwen-flutter-fused](https://huggingface.co/Wizcoderr/qwen-flutter-fused) is a Flutter/Dart-oriented code-generation model. It may assist a future Flutter adapter with boilerplate or refactoring, subject to its licence and generated-code review.
- A model is not a build engine. Hugging Face models should not generate or sign release artifacts autonomously. The release pipeline must remain deterministic: validate input, build fixed templates with Gradle/Xcode, verify package signatures, calculate checksums and store artifacts privately.

## Engineering decisions adopted in this foundation

1. **One complete submission:** accept a validated JSON payload once, persist it in PostgreSQL and as a private `request.json` manifest, then enqueue a build. A frontend wizard can collect fields step by step and make a single final POST. This avoids partially configured builds being started unintentionally.
2. **Asynchronous REST contract:** return `202 Accepted` with a stable build UUID; expose status, durable event history and Server-Sent Events. Never keep the create-build POST open during Gradle/Xcode compilation.
3. **Separate platform workers:** Linux/JDK/Android SDK/Gradle for APK/AAB; macOS/Xcode for IPA. A Vercel function is not an Android/iOS build host.
4. **Native wrapper templates:** Kotlin `WebView` for Android and Swift `WKWebView` for iOS. These are genuine installable native applications, but they remain remote-website wrappers: the website itself is not translated into native screens and must remain hosted/reachable.
5. **Tenant safety:** verify domain ownership, derive tenant identity from API credentials, isolate build UUIDs, use private artifact storage, and authorize every artifact lookup. Do not use a guessable public `/app-name/app-name.apk` path as the only access control.
6. **Signing is continuity-critical:** preserve each Android keystore for future updates. Apple distribution requires a valid Apple Developer signing identity and provisioning arrangement. A multi-customer SaaS needs a customer credential vault and KMS-backed lifecycle management.
7. **Store compliance is separate from compilation:** Android target SDK and Apple signing requirements change over time; passing Gradle/Xcode does not guarantee store acceptance.

## Additional platform references

- Android target SDK policy: https://developer.android.com/google/play/requirements/target-sdk (Google Play target API policy; this foundation uses API 36 and should be updated deliberately as requirements move).
- Capacitor iOS workflow: https://capacitorjs.com/docs/ios
- Apple distribution signing: https://developer.apple.com/help/account/certificates/certificates-overview/
- Render background workers: https://render.com/docs/background-workers
- Render persistent disks: https://render.com/docs/disks
- Vercel function limits: https://vercel.com/docs/functions/limitations
