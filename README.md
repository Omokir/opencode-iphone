# OpenCode Pocket

Native SwiftUI remote client for OpenCode V2. iOS 17+; no webview, no embedded terminal.

## Included

- Existing sessions, new sessions in a notebook directory, paged history.
- Native message composer, assistant text, tool status, interrupt action.
- Explicit allow-once / deny controls for tool permissions.
- Foreground refresh every 2 seconds, recovery after reconnect.
- Remote keep-awake switch, matching notebook Polybar mode.
- HTTPS over private Tailscale network; one-time, five-minute pairing code.
- Device-only Keychain token storage; no provider or Apple credentials in app.

## Limits

No push notifications, attachments, model switcher or interactive question forms yet.
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
