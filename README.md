# OpenCode Pocket

Native SwiftUI remote client for OpenCode V2. iOS 17+; no webview, no embedded terminal.

## Included

- Existing sessions, new sessions in a notebook directory, paged history.
- Native message composer, assistant text, tool status, interrupt action.
- Explicit allow-once / deny controls for tool permissions.
- Foreground refresh every 2 seconds, recovery after reconnect.
- Remote keep-awake switch, matching notebook Polybar mode.
- Per-chat Plan/Build switch, agent and model/variant selection, rename action.
- Native Photos and Files pickers: images, PDF and UTF-8 text/source files.
- Visible provider errors, attachment history and bounded uploads.
- iPhone control panel, expiring consent, isolated control conversation,
  reviewed one-action permissions and a Stop control for normal MCP automation.
- Per-device unread dots for completed conversations; persisted IDs/timestamps,
  automatic foreground refresh, no push/background delivery claim.
- Notebook battery on conversation list: percentage, charging/AC and low-battery
  warning, with unavailable/stale states rather than a fabricated reading.
- HTTPS over private Tailscale network; one-time, five-minute pairing code.
- Device-only Keychain token storage; no provider or Apple credentials in app.

## Limits

Native question sheets support text/options, multiple selection, booleans and
numbers, including conditional fields. External/custom field renderers still
need notebook UI. No push notifications. Attachments are limited
to 5 files, 4 MB each and 8 MB total; arbitrary binary archives are not supported.
Photos are converted to JPEG and resized to at most 2048 px. File contents are
sent through notebook to the selected model provider only when Send is tapped.
Choose a model that supports the attachment type. Listed models are enabled in
OpenCode, not necessarily authenticated or funded; choosing one may incur costs.
Tool output details remain available on notebook. Work continues on notebook when
app is backgrounded; foreground fetch resumes when reopened. Notebook must stay
awake and connected; mode cannot wake an already-suspended notebook.

## Compile

`bash scripts/build-ios.sh` on macOS with Xcode, or run **Build iPhone** in GitHub
Actions. Produces `build/OpenCode-Pocket-unsigned.ipa`, not a signed/installed app.
Use existing iLoader workflow to sign and install. Apple credentials go directly
into iLoader, never source or GitHub Actions. Personal free signing typically
requires renewal every 7 days. Distribution is private, not App Store/TestFlight.

## Notebook gateway

`bridge/server.py` binds only to `127.0.0.1:49375`. Publish only through private
`tailscale serve --bg --https=8443 http://127.0.0.1:49375` (never Funnel).
Preserve any existing Tailscale routes; do not reset Serve configuration.

It resolves the managed OpenCode service locally, reads local service password
without returning it, and exposes only allowlisted mobile operations. Mobile
access still grants substantial control through OpenCode tools: pair only your
own devices. Revocation: delete/replace `~/.local/state/opencode-iphone/token.secret`.
Disconnecting in app removes only that device's saved token.

`python3 bridge/pair.py` displays a short-lived code locally. State files are
outside repository, private to user, never committed. Rate limit: 5 attempts/minute.

## Verify

`python3 -m unittest discover -s bridge -v`

`python3 scripts/validate-ipa.py build/OpenCode-Pocket-unsigned.ipa`

Build, signing, installation, and launch are separate verification stages.

Simulator screenshots use synthetic fixtures compiled with `-D SNAPSHOT`.
The photo-picker regression additionally drives a real simulator picker using
synthetic media: attachments menu, Photos, system picker, Cancel back to chat.
These fixtures are excluded from device IPA builds. No real chat contents,
provider credentials, pairing codes or access tokens go to CI.

Control scope, host gate and signing/runtime limitations: [PHONE-CONTROL.md](docs/PHONE-CONTROL.md).

Optional local model integration test (may use provider credits):
`python3 scripts/control-policy-smoke.py`. It overrides iPhone MCP only in a
temporary isolated workspace, uses a fake device and verifies an unapproved
launch is never executed. No physical iPhone is accessed by this test.

## Unread markers

The initial server-time baseline avoids marking all older history unread after
upgrade. New completed/failed/interrupted turns get a dot unless viewed in the
active conversation. Opening and successfully loading the chat clears the dot.
State persists on this iPhone only; desktop read markers are not modified.
No polling is promised while iOS suspends the app. The list refreshes while
foregrounded and on return, without automatically replaying failed sends.
