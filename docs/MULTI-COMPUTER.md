# Multiple computers — first foundation (0.14.0)

iPhone: Menu → Computadores. Existing pairing migrates to a Keychain registry.
Add a named Tailscale HTTPS endpoint and one-use pairing code. The current
connection is not changed while pairing a second host; no existing token is
sent to the new host. Select a saved computer to switch explicitly.

Switching changes the connection generation, cancels local network monitoring
and background uploads, and recreates the conversation view. Tasks already
admitted on the previous computer continue there. Late replies from an old
connection are rejected. Draft/cache/task storage remains server-scoped.

Profiles and tokens are stored together in Keychain, not UserDefaults. The
legacy active-token entry remains for compatibility with existing transports.
Removing/revoking pairings remains distinct from switching the active host.

Android is a separate native initial client under `android/`, using the same
gateway. See its README for actual supported scope and preview-signing limits.

## Still pending

- Portable gateway adapters for macOS/Windows, including service discovery,
  filesystem operations, power and computer-use permissions.
- Shared KzL memory/coordinator independent of one host. Current KzL is per host.
- Android feature parity (voice, files, approvals, drafts and notifications).
- A structured computer-use activity/card and authorized image transport.
- Stable Android release signing and physical-device acceptance testing.

No global root access, automatic approval, screen-control capability or remote
wake functionality is introduced by adding a profile.
