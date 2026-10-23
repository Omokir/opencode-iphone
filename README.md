# OpenCode Pocket

Native SwiftUI remote client for OpenCode V2. iOS 17+; no webview, no embedded terminal.

**Instalação e uso em português:** [tutorial completo](docs/GUIA-PT-BR.md).

Daily-use improvements and limits: [0.6.0 cache, queue and privacy](docs/QUALITY-0.6.md).

Projects/system integrations: [0.7.0 supported features and pending limits](docs/WORKFLOWS-0.7.md).

## Included

- Existing sessions, new sessions in a notebook directory, paged history.
- Native message composer, assistant text, tool status, interrupt action.
- Explicit allow-once / deny controls for tool permissions.
- Session-scoped foreground SSE updates, periodic fallback and reconnect recovery.
- Conversation-name search across server history, with pinned matches and pagination.
- Remote keep-awake switch, matching notebook Polybar mode.
- Per-chat Plan/Build switch, agent and model/variant selection, rename action.
- Native Photos and Files pickers: images, PDF and UTF-8 text/source files.
- Visible provider errors, attachment history and bounded uploads.
- iPhone control panel, expiring consent, isolated control conversation,
  reviewed one-action permissions and a Stop control for normal MCP automation.
- Per-device unread dots for completed conversations; persisted IDs/timestamps,
  automatic foreground refresh, no push/background delivery claim.
- Pin/unpin conversations via swipe or context menu, with a pinned section at
  the top of the chat list. Pins persist per iPhone/server and older pinned chats
  are fetched even when outside the first page; desktop metadata is untouched.
- Notebook file browser with protected roots, bounded binary download/upload,
  checksums, version-checked overwrite confirmation and upload receipts.
- Opt-in foreground phone inbox: a Files-visible app folder uploads direct files
  to a dedicated notebook folder, then removes matching local originals only
  after re-reading and verifying committed remote contents. See [folder guide](docs/INBOX.md).
- Local protected drafts (text and existing chat attachments), attachment
  thumbnails/Quick Look previews and event-driven foreground response updates.
- Notebook battery on conversation list: percentage, charging/AC and low-battery
  warning, with unavailable/stale states rather than a fabricated reading.
- Codex weekly quota from local authenticated app-server read-only API, with
  reset time and explicit account/source scope. No message-count estimate.
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
requires renewal every 7 days. Installation uses sideloading, not App Store/TestFlight.

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
File-transfer/draft/live-update boundaries: [FILES-AND-LIVE-CHAT.md](docs/FILES-AND-LIVE-CHAT.md).

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

## Codex quota

The notebook launches a bounded, stdio-only `codex app-server` client and calls
only initialize, account/read (refreshToken=false), account/rateLimits/read.
No thread/turn, login, purchase or reset-credit action is started. It returns
only masked account label and sanitized quota windows; no tokens or account
response body reaches the phone or logs. Results cache for 60 seconds (manual
refresh is throttled to at least 10 seconds).

A weekly window is recognized by its supplied 10080-minute duration, not by
whether it is named primary/secondary. Missing data is unavailable, not zero.
These are limits of the ChatGPT account connected to Codex CLI on notebook;
they are not API balance and may differ from the account used by a chat model.
