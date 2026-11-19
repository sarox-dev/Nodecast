# Security remediation, 2026-11-18

This change starts from Core ccbcaff4441eadee394aa369737142319ef2a977 and pairs with Extension 4add5ae8dbe00b73a3d0eee24c4e92488ee8357f.

The compatibility goal is to retain local and Trusted LAN access, account switching, capture, Ask, existing data and Docker/native launch paths.

## User-visible behavior

- A fresh installation requires the setup code printed by its installer or read locally from `contents/.setup_token` before creating the owner. Existing accounts continue to sign in normally. This also permits first setup from a LAN browser.
- Extension pairing opens an extension-owned confirmation tab showing the destination origin. Approve it within 90 seconds. LAN IPv4 addresses and LAN hostnames are supported.
- Extension credentials migrate from browser sync to device-local storage. UI preferences continue to work on the current device.
- Only the paired Core origin can read account status or synchronize settings. The confirmation tab requests browser access for the selected server host; declining preserves the previous connection.
- Public AI provider endpoints require HTTPS. Explicit local Ollama/LM Studio providers retain HTTP support.
- Session secrets rotate when a new account signs in. Accounts already authenticated in that browser are retained. Extension tokens bound to the replaced session require the existing reconnect flow.
- Unsafe links render as inert destinations. Quotes and HTML characters in existing saved titles remain visible text.

## Audit disposition

| Original finding | Current state |
| --- | --- |
| 1. Stored XSS | Attribute escaping repaired in all four frontend helpers. External link schemes validated in cards, source groups and renderers. Metadata keys and stored timestamps escaped in legacy renderer. Real Chromium regression fails on baseline and passes after patch. |
| 2. Extension reconfiguration | Sender origin is checked in the worker. Pairing requires approval on an extension-owned page. Settings are stored after candidate validation. Disconnect requires the currently paired Core origin. |
| 3. Synthetic capture | Content-script shortcut, save buttons and reason submission require trusted browser events. Context menu, popup and commands paths remain available. |
| 4. LAN HTTP | LAN functionality retained. TLS deployment remains open. The patch does not claim that unencrypted LAN traffic is confidential. |
| 5. First owner takeover | Local setup secret required for first-owner registration, including LAN. |
| 6. Release trust | Actions pinned to fetched commit SHAs in both repositories. Immutable releases, independent provenance verification and release protections remain deployment work. |
| 7. Synced credentials | Migrated to device-local storage and removed from sync. Browser/OS account compromise remains outside this boundary. |
| 8. Excess collection | Layout lookup strips URL query and fragment. Full DOM capture retained for existing extraction behavior. Data-minimization redesign remains open. |
| 9. Snapshot remote resources | Open. Removing images/fonts would change existing snapshot rendering. |
| 10. Provider transport/SSRF | Public HTTP rejected, local configured providers retain HTTP. DNS validation-to-connect binding remains open for custom providers. |
| 11. Recovery interference | Fresh anonymous request no longer supersedes a recently approved request. Administrators still need to verify the requester through a trusted channel. |
| 12. Session fixation | New secret and newly authenticated membership replace the old session in one write transaction. A separate SQLite reader verifies that the new account is never committed under the old secret. Existing single-session revoke SQL also corrected. |
| 13. Resource/cost limits | Open. Existing request and raw-storage caps retained. Snapshot type and serialized-size accounting corrected. Raw quota checks, writes and deletes now share a per-user SQLite write lock across processes, and failed writes clean up their own partial capture. Instance-wide quotas and AI concurrency/cost budgets remain work. |
| 14. PyJWT | Updated to 2.15.1. Oversized and recursive malformed tokens rejected. |
| 15. Local file permissions | Unix installer uses private umask, generated JWT secret is created privately. Windows installation root/updater ACL and existing data/backup permissions require platform validation. |
| 16. Updater availability | Installer is downloaded and verified before stopping the service. Active session count now uses recent session activity. Host updater network requests have finite connect/response timeouts. Full archive staging, consistent SQLite backup and automatic rollback remain open. |
| 17. Third-party script | D3 7.9.0 and its license are shipped with the application. |
| 18. Browser/network policy | Default nosniff, same-origin referrer policy and DENY framing headers added. TrustedHost/reverse-proxy and Origin policy tightening remain open to preserve existing LAN aliases pending deployment verification. |
| 19. Health metadata | Open. Existing host updater health contract retained. |
| 20. Isolation/build reproducibility | Dockerfile now defaults to non-root even outside Compose. Native isolation, image digest and complete dependency lock remain open. |
| 21. Personal registration race | Public policy rechecked in an insertion transaction. Administrative creation also checks profile limits within its write transaction. |

## Validation

- 208 pytest checks passed, including real Chromium attribute-injection regression, LAN IP/hostname/localhost login/logout, initial setup, concurrent registration, session rotation, approved recovery preservation and renderer inputs.
- Four existing Core JavaScript scripts passed. Extension metadata and security scripts passed with browser API mocks. Real Chromium also verified Enter-to-save in the closed-shadow floating control after rejecting synthetic interaction.
- Docker image built using declared dependencies. Read-only, non-root container with dropped capabilities started. Setup denial/approval and authenticated API/logout checks passed.
- Bash syntax checks passed. Git diff whitespace check passed.
- Added CI matrix for Python/JavaScript checks on Linux, Windows and macOS, plus Windows PowerShell parsing and Linux Chromium.
- Real Windows Task Scheduler/macOS launchd installation, live browser-extension installation and multi-device LAN operation are pending. API tests exercise LAN origins, not a second physical machine.
- Existing FastAPI/Starlette deprecation warnings remain.

## Follow-up fixes

- Repeated installation preserves a valid HTTPS public origin for the same LAN hostname, including a reverse-proxy port differing from the application port. Changing network profiles or hostnames still computes the corresponding default address.
- Sensitive account actions share one failed-password budget. Existing legacy account administration and recovery-code rotation now use it too. Successful verification clears that account/client budget. Anonymous recovery requests also have a client-wide budget.
- Two-process regression reproduces raw-quota overbooking on the previous patch and passes with serialized writes. A simulated HTML-write failure also reproduces a stranded capture on the previous patch and passes after cleanup.
- Added Bash and PowerShell origin behavior checks, plus API tests for both failed and successful account operations.
- These changes continue in Core PR #1. The Extension PR is unchanged in this follow-up.

The remaining items above are explicitly unfinished. This branch must not be described as closing all 21 audit findings.
