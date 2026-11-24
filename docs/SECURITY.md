# Security design and deployment controls

## Mandatory controls already present in this foundation

- API key authentication is tenant-scoped; `owner_id` comes from the configured credential, not the JSON body.
- Rate limits are keyed by owner and stored in Redis.
- CORS is configured with explicit origin allowlists.
- HTTPS URLs only; credentials and nonstandard ports are rejected.
- Domain ownership must be proven by a DNS TXT challenge before a site can be packaged.
- The domain's DNS A/AAAA answers are checked for public addresses during challenge setup and again immediately before a build is queued; production still needs network-level egress isolation and DNS-rebinding tests. The worker does not download/crawl the site.
- Workspaces use owner-hash + UUID paths; artifact paths are UUID-scoped.
- Download queries check build ownership and canonical storage path; S3 downloads are short-lived presigned URLs.
- Android WebView disables cleartext traffic, file/content access, mixed content, and SSL-error bypass; only configured trusted hosts remain in the embedded WebView.
- External web origins are opened in a browser surface, not navigated with the trusted app WebView context.
- Release signing material is stored outside the public web root and passwords are derived from a stable master secret.

## Mandatory controls still required before production

1. Put TLS in front of the API and set `PUBLIC_BASE_URL` correctly.
2. Do not expose `X-API-Key` to browser JavaScript. Use the authenticated PHP backend as a server-side façade, or implement short-lived user-scoped tokens.
3. Move API key storage to a secret manager and support key creation, rotation, expiry, and revocation.
4. Use a secrets manager/KMS for Android signing passwords and Apple certificates/profiles. The deterministic Android key derivation is an initial managed-signing mechanism, not a replacement for a hardened credential vault.
5. Ensure object storage blocks public access, encrypts at rest, has lifecycle expiration, and has bucket-level access policies.
6. Run build workers as non-root with read-only base filesystems, CPU/memory/PID/time quotas, no Docker socket, and no privileged mode.
7. Restrict worker network egress. The Android build process needs access to approved dependency repositories; it should not have unrestricted access to cloud metadata, databases outside its service network, or arbitrary private subnets.
8. Add per-job containers or VMs. A tenant build must not access another build's workspace, signing files, environment, or credentials.
9. Add antivirus/content inspection for user-uploaded icons and future ZIP uploads. Limit decompressed archive size, file count, and path traversal if ZIP-source builds are added.
10. Validate all web URLs server-side at build creation and repeat critical validations in the worker. Apply DNS-pinning/egress protections if any worker later fetches websites/assets.
11. Add account-level quotas, concurrency quotas, request body limits at the reverse proxy, and abuse monitoring.
12. Add audit trails for domain verification, build initiation, signing key creation, download, and key access.
13. Back up the signing root and master key in separate secure locations. Test restore before real customer apps are signed.
14. Complete penetration testing and Android/iOS runtime tests with malicious redirect chains, custom URL schemes, spoofed hostnames, and untrusted external links.

## Screenshot limitation

Android can block screenshots and screen recording for the app window with `FLAG_SECURE`. iOS does not offer a supported general-purpose API for third-party apps to reliably prevent user-initiated screenshots. The iOS worker must show a warning when `allow_screenshots=false`; it must not claim that this setting is enforced on iOS.

## WebView trust model

Only the verified website host (and its subdomains) is allowed to navigate inside the embedded app WebView. Other HTTP(S) hosts are opened through an in-app browser or the system browser. Do not add a JavaScript-to-native bridge by default. If native bridge methods are added later, expose a narrow allowlisted API and test origin, frame, navigation, and permission boundaries.
