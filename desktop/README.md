# KzL Agent Linux 0.7.0 · Darktech

Native darktech identity follows the conversation-first web prototype: near-black
canvas, graphite surfaces, red primary action/selection, restrained technical
monospace accents and the unchanged original avatar. First launch of this design
selects dark mode once (`darktech_v1`); subsequent theme choices persist normally.
Light/system modes remain available. Main window and dialogs synchronize theme;
44px composer actions, keyboard focus, contrast and portrait layout are retained.
No decorative animation or browser/webview is introduced. `smoke_darktech.py`
captures native desktop/414px and checks default/theme/dialog/draft behavior.

Permission/form read failures no longer discard successful message reads. Each
review category retains its last snapshot but disables stale controls; a healthy
category stays usable. Failed message reads retain prior history and fence both
review categories. Previously open reviews invalidated by an outage require
reopening after recovery, not merely another click. `smoke_partial_reads.py`
checks independent failures, continuing message updates, stale-dialog fences and
manual read recovery without automatic replies or provider execution.

Main-window keyboard shortcuts: **Ctrl+F** opens local loaded-message search;
**Ctrl+N** invokes the existing guarded new-chat flow. They do not act behind
review/save dialogs. Enter/Shift+Enter composer behavior is unchanged. Settings
lists the shortcuts. `smoke_shortcuts.py` injects actual X11 keys only on private
Xvfb: search typing sends nothing, Ctrl+N behind a dialog creates nothing, and
main-window Ctrl+N creates one synthetic chat while preserving the prior draft.

Pairing is single-flight across settings windows; repeated clicks cannot submit
the same active attempt. Failed acknowledgement requires entering a fresh code,
not automatic replay. Successful pairing acknowledgement survives navigation and
refreshes read-only state without reopening another chat over the current one.
`smoke_pairing.py` starts with expired fixture credentials, fails one attempt,
delays a fresh-code attempt through chat navigation, then verifies authenticated
reads, 0600 credential persistence and both preserved drafts. No actual account
is paired by this test and no real codes/credentials are captured in test logs.

Free-text/numeric form answers now expose their field titles and required status
as explicit accessible names. Model/mode selectors retain their selected-value
names plus purpose descriptions; the optional variant field has an explicit name.
`smoke_accessibility.py` uses a separate real AT-SPI reader on private D-Bus/Xvfb
to verify six native control names/descriptions/roles, rather than inspecting
only visible Gtk.Label text. Run with `GTK_A11Y=atspi`. This is bounded integration
coverage, not a screen-reader or WCAG conformance certification.

Resources → **Buscar nas mensagens carregadas** searches a plain-text snapshot of
loaded user/assistant messages, separately from sidebar conversation-name search.
Literal case-insensitive queries are capped at 256 characters and 100 matching
messages; context snippets are bounded. Tool/config/file data is not searched.
Choosing a result scrolls to its existing native message widget; a stale result
cannot jump into another chat. No older-page fetch or provider request is made.
Reopen search to include subsequently loaded/updated messages. `smoke_search.py`
checks literal Unicode queries, native jump geometry and navigation guards.

Conversation tool disclosures now count running, streaming-input, failed,
unconfirmed and completed tools separately. No longer labels every non-running
tool as completed. Expanded review shows literal tool names and explicit failures,
with bounded raw details behind a second read-only disclosure (first 100 tools,
12,000 characters per detail; overall counts include all tools). Unknown statuses
remain unconfirmed. Rendering never executes a tool, opens a link, or grants a
permission. `smoke_tools.py` checks running/error/unknown/completed transitions
and literal potentially active-looking names/errors with synthetic messages.

Resources → **Salvar conversa carregada (.txt)** exports a reviewed UTF-8 snapshot
through the native save chooser, including an explicit partial-history notice.
Only loaded user/assistant text is included: no unsent draft, attachment bytes or
URIs, tool details, system messages or private configuration. It is literal text,
not an HTML export; conversation text itself may still contain sensitive data.
The snapshot stays bound to its original chat after navigation. Writes are atomic
with private 0600 permissions; existing files require replacement confirmation.
Export above 8 MiB is refused without truncation. No extra history/network fetch
or provider call is made. `smoke_export.py` covers native chooser cancellation,
snapshot binding, private save and cancelled overwrite; pure tests cover omitted
fields and size limits.

Persistence warnings now survive chat navigation and healthy background reads;
only successful local persistence clears their storage notice. Drafts and small
attachments remain in memory for each chat during a write failure. Recovery saves
the entire state, not only the currently visible draft. `smoke_draft_switch.py`
injects a write failure, edits two chats, restores storage, then launches a fresh
GTK process to verify both exact drafts/attachments and zero automatic writes to
the gateway. Forced termination before a successful save can still lose edits.

Closing the main window first saves its final private state snapshot. If that
write fails, close is blocked before worker/media teardown and the editable draft
remains open. A single warning offers continued editing or retrying save/close;
there is no silent discard. This cannot protect against forced process kill or
power loss before persistence. `smoke_disk_failure.py` injects an OSError without
filling any real disk, verifies old preferences/current UTF-8 text stay intact,
then restores storage and checks fresh-state recovery after normal close.

Older-message pagination is single-flight and keeps the current history/cursor
after read failures. Retrying remains a manual GET. Prepended rows preserve the
reading offset instead of jumping to the bottom; overlapping older IDs cannot
replace newer message content. Repeated cursors stop pagination with an explicit
warning, not an infinite request loop. Late pages cannot enter another chat.
`smoke_pagination.py` checks long-history geometry, retry, duplicate clicks,
overlap precedence and navigation with synthetic read-only data.

New-chat creation records intent durably before POST. A lost response or process
interruption blocks another creation for the same requested project until explicit
history review; no ID/title heuristic guesses that an arbitrary recent chat is
the created one. The review dialog refreshes history using GET and requires separate
confirmation to unlock a later manual attempt. Review itself never creates a chat.
Delayed success records the returned session ID even after navigation without
opening it over an unrelated conversation. Unknown creation records are retained
under a 100-record limit; only acknowledged/reviewed records can be evicted.
`smoke_creation.py` checks lost responses, state reload, review cancellation,
manual unlock and navigation with a synthetic transport, no provider calls.
`smoke_review_recovery.py --kind creation` adds an actual process-kill/restart
check after authenticated fixture admission and before its HTTP acknowledgement.
The fresh GTK process restores the unrelated last chat and its draft, refuses
another creation for the pending project, and finds/opens the admitted chat by
GET-only history plus explicit selection. The fixture requires exactly one
creation POST and no restart retransmission. Finding a plausible history entry
does not automatically clear the unresolved creation record.

Permission and form replies now persist a local action record before HTTP and
remain bound to their original conversation/project. Duplicate/stale confirmations
are refused; delayed acknowledgements are recorded even after navigation. Failed
responses stay uncertain and locked rather than enabling blind replay, including
changing an uncertain permission decision from allow to deny. Acknowledged review
IDs cannot be answered again while their journal record is retained. Existing
phone-control and oversized-permission approval restrictions remain enforced.
`smoke_reviews.py` checks delayed/failing replies, context switches and draft
preservation using synthetic transport only; no real permission is granted.
`smoke_review_recovery.py` additionally kills only its owned sandbox GTK clients
after authenticated fixture receipt but before acknowledgement, then starts new
clients from the same private state. Permission/form records remain unresolved
(`attempted` is not completion), reopened replies stay blocked, the original
session/project is retained and another conversation's draft survives. Exactly
two initial replies and zero restart retransmissions are required. A successful
server-side effect cannot be inferred from an unresolved local record; review
the actual pending request/effect before manually clearing uncertainty.

Rename and interrupt now share the durable action journal. Stale confirmations
are refused, duplicate clicks are fenced, and acknowledgements survive navigation
without altering the current unrelated conversation. Rename confirms only through
matching original-session title read-back, including when the PATCH response is
lost. Failed read-back stays uncertain and locks replay pending local review in
Resources. An interrupt acknowledgement means request received, never proof that
execution stopped. `smoke_mutations.py` covers delayed responses, failed reads,
context switches, repeated clicks and uncertain replay locks with no provider.

Settings recovery is also checked across separate GTK processes: two accepted
writes followed by failed confirmation read remain unconfirmed; restart restores
server mode, model and variant without replaying either write. Variant read-back
must match even when the requested variant is empty; a server-retained variant
keeps review open and displays the actual value. A model returned outside the
original dialog catalog is added as the saved choice instead of leaving a stale
selection. See `smoke_options_recovery.py` and `smoke_options.py`.

Model/mode settings are bound to the displayed conversation/project. Save is
single-use per dialog; partial writes are not retried automatically. The client
reads back actual session settings after success or failure and closes only when
the requested values match. Failed read-back leaves an explicit unconfirmed state
and a GET-only review button. Navigation cannot apply an old response to the new
chat. Reopening reflects actual partial state, not an assumed rollback. An absent
current model stays selectable rather than silently choosing the first catalog
entry; the current server default can likewise be left unchanged.
`smoke_options.py` checks partial failure, duplicate/stale saves and read-back.

Activity now provides native read-only review sections: file paths with change
counts and literal patches, terminal screen text, and tasks filtered to the
original conversation. Each section refreshes independently using GET only;
navigation cannot retarget an open review. A terminal read failure leaves diffs
and tasks visible. Task receipt is not completion, and unconfirmed live states
are explicitly marked. Patch/task previews are capped at 12,000 characters per
item and 100 items; terminal text is capped at 100,000 characters. Copy preview
copies only displayed text; nothing applies a patch or executes terminal output.
`smoke_activity.py` covers literal patches, independent failure and navigation.

Conversation polish follows the local web prototype without embedding a browser:
quieter model controls, voice beside the message draft, outlined composer, 44px
voice/send targets, keyboard focus outlines and a framed original-avatar identity.
System fonts/themes remain native. No new motion is introduced. `smoke_polish.py`
checks portrait target bounds, keyboard focus and unsent draft preservation across
theme/format changes. These checks do not constitute screen-reader certification.

Commands and skills now persist admission intent before HTTP submission and keep
their original conversation/project binding across navigation. Lost responses
lock replay until explicit local review; a 204 acknowledges the request, not task
completion. No unsupported idempotency fields are sent. Resource refresh shows
queued entries and action records. Inbox reconciliation requires matching session,
user type and queue/steer delivery; foreign or synthetic evidence cannot clear a
draft. Edited drafts remain intact. `smoke_actions.py` exercises lost responses,
stale confirmations, navigation during execution and queue reconciliation using
only an isolated authenticated fixture.

Native **GTK4 + libadwaita** application. No browser, Electron or webview.
Uses the existing Pocket gateway on `127.0.0.1:49375`; does not replace or alter
the iPhone app, gateway service, providers or Apple signing material.

## Open

After user-local installation, search for **KzL Agent** in the application
menu. Right-click actions offer **Modo retrato** and **Demonstração sem API**.
Alternatively:

```sh
~/.local/bin/kzl-agent
~/.local/bin/kzl-agent --portrait
~/.local/bin/kzl-agent --demo
```

The phone button in the title bar toggles a **414 px usable portrait viewport**.
Desktop mode has a permanent history sidebar and a clamped reading column.
Portrait hides that sidebar; the history button reveals it. Native window
decorations, typography, file chooser and keyboard are Linux controls, not
SwiftUI or an assertion of pixel-identical iOS rendering.

Requires Python 3, PyGObject, GTK4 and libadwaita; already available on this Linux.
Native Markdown uses Python-Markdown 3.x (3.10.3 is already installed here).
Live additionally uses native GStreamer WebRTC/Opus/libnice plugins, also
available here. No browser or webview is used for media or signaling.
The interactive local terminal uses installed GTK3/VTE 2.91 in a separate
process so GTK3 and GTK4 are never mixed inside one Python process.
No package installation or sudo required here. To install/update reviewed source:

```sh
python3 desktop/install.py
```

Installer creates only its manifest-owned application files, launcher and menu
entry. Unknown edits are preserved and stop an update. User preferences and
conversation data are never removed during installation.

The product name is unified as **KzL Agent** across Linux and iPhone. Legacy
application IDs, state paths, repository names and the `opencode-pocket` launcher
remain unchanged/compatible to preserve pairing, drafts, history and OS identity.
The iPhone display name changes only after installing its next rebuilt update;
editing the source does not rename the already installed iPhone binary.

## Working with real conversations

Default launch connects to the existing local Pocket gateway, using a dedicated
desktop token when present, otherwise the existing local legacy token if still
authorized. Tokens never enter logs, CLI arguments or source. If authorization
is missing or revoked, open **Ajustes → Parear computador** and enter a code
from the existing pairing shortcut. No iPhone is needed. Dedicated desktop
credentials are stored in a private `0600` connection file under the user's
`0700` state directory. Revoke that registration using Pocket device management.

Opening history never sends a prompt. Sending messages, approving permissions,
activating skills or invoking commands can execute tools and consume the selected
provider, exactly as through the gateway. No automatic paid voice requests.
Network work runs off the GTK thread. History refreshes every 1.2 seconds, not
through native iOS SSE. Changing conversations invalidates stale read callbacks.
Uncertain writes are not automatically retried. An unchanged prompt keeps its
request ID across manual retries and application restarts.
An admission-intent journal is saved before transmitting a prompt. Attempted or
uncertain sends remain visible after a process interruption and are never
automatically resubmitted. Read-back of the matching user-message ID marks
admission (not task completion). Only an unchanged matching draft is cleared;
new user edits are preserved. Later transport errors cannot downgrade confirmed
admission. Unresolved journal records are not evicted to make room for new work.
If the gateway is absent at startup, the client reconnects using GET-only reads
for history, catalog and last-session metadata. Each read flow is single-flight,
with failure delays of 2/4/8/16/30 seconds; manual reads can bypass the delay but
not overlap the same flow. A valid empty catalog/history is a successful result,
not a reason to create a replacement chat. Manual searches coalesce while an
older list read is active. Stale last-chat results cannot change a later user
selection. Temporary read warnings clear only their own connection notice;
uncertain-send and unrelated action warnings are not erased by a healthy GET.

Implemented work flows:

- Conversation history/search and pagination, restoration of the last chat.
- One-tap new chat using Core defaults, native project-directory chooser.
- Local chat pins and favorite project directories.
- Renaming, Build/Plan, provider/model selection and optional model variant.
- Native multiline composer: Enter sends, Shift+Enter inserts a line.
- Private persistent per-chat text/attachment drafts; 5 files, 4 MB each,
  8 MB combined. Images, PDF and UTF-8 text/source. Draft clears only after
  acknowledgement; editing is disabled while sending to avoid losing changes.
- Progressive response refresh, native Markdown headings, emphasis, strikethrough,
  ordered/nested/task lists, blockquotes, separators, tables and code rendering,
  code copying, collapsible tool details, visible provider errors, interruption.
- Explicit permission review/deny/allow-once, with a second confirmation before
  granting. Physical phone-control grants remain disabled on desktop.
- Native typed question controls, required fields, options, booleans, numbers,
  integer validation and conditional visibility.
- Existing project commands and skills, with explicit execution confirmation.
- Native schedule calendar/time controls, list, pause/resume and delete; each
  mutation requires confirmation and uncertain responses lock further writes.
- Gateway file browsing and native save/download chooser. Existing destination
  requires explicit replacement consent. Downloads verify SHA-256 and byte
  count, use version preconditions when supplied and publish saved files
  atomically without truncating an earlier file on failure.
- Assistant local Markdown file references have a save action. The gateway
  resolves the parent into an approved root and checks the file exists/readable
  before opening the save chooser. Remote URLs, traversal and control-character
  paths are rejected. A reference is not proof that generation succeeded.
  Uploaded-message attachment cards remain metadata-only because history strips
  their original bytes; arbitrary provider sandbox files are not local files.
- Dedicated resumable upload center (sidebar up-arrow or Files → Enviar arquivo
  grande). Native source chooser, explicit consent, private persistent journal,
  manual pause/resume, bounded 4 MiB chunks, per-chunk/full SHA-256 and a separate
  committed-content verification read. No original is deleted or moved, even
  after success. A completed path can be copied or inserted into a draft without
  sending a prompt. Large binary transfers are separate from chat attachments.
- Read-only execution diff, terminal output, KzL tasks and computer status.
- Interactive **local project terminal** via the terminal icon beside chat
  controls. It first resolves/displays the canonical local directory and asks
  for confirmation, then opens a separate native GTK3/VTE window with the user's
  interactive shell. Paths are cwd/argv data, never interpolated into `cd` or a
  command string. Demo mode cannot start a shell. Closing the main chat window
  does not automatically close independently opened terminal windows.
- Native light/dark/system theme and persistent portrait preference.
- Native tables support alignment, horizontal scrolling and TSV copying. Code
  blocks use selectable, non-editable GTK text views with horizontal scrolling;
  copying preserves literal tabs (including Makefiles). Incomplete root fences
  get a preview while a response streams. Stable message widgets and selected
  text are retained when another message updates instead of rebuilding history.
- Safe external links require a native confirmation showing the normalized full
  destination before opening the Linux default application. HTTP(S) and strict
  mailto links are allowed; scripts, file-launch URLs, credentials, header-bearing
  mail links, control/bidi characters and ambiguous IDN mappings are rejected.
  IDNs that round-trip unambiguously are displayed as ASCII/punycode.
  Local Markdown file references still resolve only through gateway save actions.
- Native Live window: explicit paid-call disclosure on every start, bounded
  recent-chat context, captions, microphone mute, end, and a 3-minute time limit.
  Read-only model availability is checked before opening media. The microphone
  starts muted and is enabled only after the remote session acknowledges its
  configuration; a mute selected during connection remains muted.
- Voice task proposals are displayed for human review, deduplicated by call ID,
  and sent to the bound conversation only after a separate explicit confirmation.
  Pending review is not admission or completion. Uncertain task sends retain
  their request IDs locally and are never automatically repeated. Ending voice
  does not interrupt already admitted OpenCode work.
- One short local synthetic output test (no microphone or network) and manual
  copy of the latest input transcription. Audio is not recorded to disk by this
  client. Starting a real call sends audio/transcription/context to OpenAI and
  uses separate API billing, not the Codex subscription.

Private state: `~/.local/state/opencode-pocket-desktop/` (or `$XDG_STATE_HOME`).
Demo uses a separate `opencode-pocket-desktop-demo` directory and in-memory
synthetic conversations. It never reads the real connection token or uses APIs.

### Resumable transfer details

The existing gateway protocol targets its dedicated inbox under the notebook's
home directory (currently the legacy-named `Downloads/Iphone 11 Omoki`). It is
**not** a general resumable writer to arbitrary project folders. Names include a
stable UUID; existing files cannot be silently replaced. The protocol cap is
1 TiB; automated large-file evidence covers >9 MiB, not a physical TiB transfer.
Buffers are bounded to 4 MiB and the source is streamed rather than copied into
client cache. Source identity/stat changes stop that upload; new contents need
a new transfer identity. UTF-8 names are bounded for the destination filesystem;
protected credential filenames and source symlinks are rejected.

Each resume first checks for an already committed file. Only an explicit 404
allows reading durable partial offset and sending missing blocks. Authentication
errors, conflicting receipts and transport errors never masquerade as 404. A
lost chunk acknowledgement is reconciled by offset; a lost commit acknowledgement
is reconciled by reading the actual destination, without re-uploading its bytes.
Cross-process file locks prevent two writers for the same UUID. Journals are
private (`0600` in a `0700` transfers directory), locked and atomically updated.
Restarting does not start any network writes; the owner must press Resume.

Closing the transfer panel leaves an authorized job running. Closing the app
requests pause; an in-flight block or commit may still finish. No background
upload service or automatic folder sync is installed. Removing a completed list
entry removes only local metadata, not files. Abandoned server partials are not
automatically deleted; the current gateway has no dedicated abort/cleanup route.

### Native Markdown boundaries

This is a GTK document viewer, not an embedded HTML page. Python-Markdown's raw
HTML processors are disabled; an inert intermediate tree is translated into GTK
labels, lists, grids and text views. Only generated, escaped Pango formatting is
used. Raw HTML/scripts remain literal text. Markdown images show alt placeholders
and **never** fetch their URLs automatically; code blocks never execute. External
links do nothing until reviewed and confirmed. Markdown links inside code examples
do not become generated-file actions.

Parser/display budgets protect the interface: 200,000-character parsing preview,
128 root fenced blocks, bounded node/depth/component counts, first 80 table data
rows and 12 columns, and a 100,000-character code display preview. Limits are
announced, not presented as full output. Table copying includes analyzed rows;
code copying includes the analyzed block; limited documents offer full-message
copy. Clipboard text normalizes line endings to LF and replaces invalid control
characters; ordinary fenced code tabs remain unchanged. Original binary bytes
belong in verified file transfers, not the text clipboard.

The parser follows Python-Markdown semantics, not a claim of complete CommonMark
or GitHub parity. Fence attributes/titles are ignored; specialized nested-fence
dialects, LaTeX math, diagrams, arbitrary HTML/CSS and remote image previews are
not implemented. Ordinary headings/lists/tables/links/code are covered by both
parser and actual GTK interaction tests.

### Local terminal boundaries

This is **not** an iPhone/remote shell endpoint. The gateway's terminal output
remains read-only and its route allowlist was not broadened. Opening a local
terminal explicitly grants the normal logged-in user's shell authority; it is
not a sandbox in production. User shell configuration/startup files and shell
history behavior remain the user's. Chat, Markdown and voice output are never
automatically fed to the terminal. Terminal output is not recorded by this helper.

Copy uses plain text. Paste is read only after a user action, capped at 64 KiB,
rejects terminal control/directional characters and requires native review for
multiline text. It pastes the exact reviewed snapshot even if the clipboard
changes meanwhile. Primary-selection middle click and Shift+Insert follow the
same guarded path; unreviewed drag/drop input is disabled. Multiline paste can
execute commands after confirmation depending on the shell's bracketed-paste
behavior. OSC hyperlinks and sixel are disabled, window-title escape requests
are ignored, and native VTE scrollback is capped at 10,000 lines. Current VTE
0.84.1 also passed the fixture proving OSC 52 did not alter the clipboard.

Closing a live terminal asks for confirmation and requests SIGHUP on the spawned
shell through its Linux pidfd, then waits for exit before destroying the window.
It no longer calls `set_pty(None)` on a live session: that path reproduced a VTE
segmentation fault in the active-close fixture. If the shell does not exit, the
window remains usable and asks the user to use Ctrl-C/exit; no automatic SIGKILL
or signal to an arbitrary PID/process group is performed. Closing during startup
cancels the async spawn and handles its completion before teardown. Local commands
may be interrupted. This does not cancel work already admitted by Core.

## Verification and remaining scope

Automated tests run with an empty allowlisted environment, read-only source,
an isolated loopback network, private Xvfb/D-Bus, no host credentials, bounded
scratch files and CPU/memory/process/time limits. Tests cover backend contracts,
installation hashes/refusal of unknown edits, actual GTK interactions, draft
restoration, attachments, send acknowledgement, permissions, rename, typed forms,
model/mode controls and 414 px portrait. Connected-mode GTK tests use a separate
dummy gateway, not a provider account or the installed live service.

This is a first native Linux release, **not a claim of 100% OpenCode/Codex parity**.
Read-only live integration returned HTTP 200 for history, catalog (135 models),
messages, permissions, forms and diff. No live writes or provider prompts were
submitted during that check. Real-provider execution still needs acceptance.
Project-scoped command/skill reads also returned HTTP 200 (18 commands and 46
skills in the sampled project). Schedule listing returned HTTP 403 with
`Scheduled tasks are disabled; set experimental.schedules in config`.
The desktop UI reports that disabled state and does not change OpenCode
configuration or enable autonomous executions automatically. Schedule writes
are verified only against fixtures until the owner authorizes that capability.
The real voice model availability endpoint returned HTTP 200 with
`gpt-realtime-2.1` available over WebRTC. No real voice session was created.

Additional isolated evidence:

- Actual GTK save chooser → authenticated fixture file context/list/download →
  SHA-256/length verification → atomic saved bytes. A second download with an
  intentionally wrong hash failed without altering the earlier file, even
  after native and application replacement confirmations.
- Native billing dialog cancellation and ending while the availability read
  was delayed: zero paid broker calls, zero microphone/media pipelines opened.
  Queued broker creation also checks a cancellation token before transmission.
  An already transmitted request can still have been charged and is never retried.
- Resumable upload tests use the **real bridge PhoneInbox/ResumableInbox engines**
  behind a separate authenticated fixture HTTP server. They cover >9 MiB in
  bounded chunks, empty files, short local reads, pause/restart/resume, lost chunk
  and commit acknowledgements, changed sources, bad offsets/receipts, 401 during
  verification, protected names, cancellation and concurrent-writer exclusion.
  The GTK flow selects a source, confirms, pauses after a durable 64 KiB chunk,
  reloads the journal into a fresh manager, resumes, verifies actual bytes/SHA-256
  and inserts the confirmed path into a draft. No original is deleted and no
  provider prompt is submitted.
- Native Markdown tests inspect headings, tables, list nesting/numbering and
  readonly tasks; preserve code tabs and table TSV through the actual private
  clipboard; cancel/confirm safe link actions without launching a real browser;
  block unsafe URLs and observe zero tracking-image requests. Real wheel events
  scroll to the code section for a distinct screenshot. Desktop, 414 px portrait
  and dark captures were reviewed; wide tables/code scroll horizontally rather
  than widening the portrait window. Streaming retains stable widgets/selection.
- Native terminal tests start `/bin/sh -i` in the isolated home/network/Xvfb,
  exercise actual PTY input/output, ANSI and UTF-8, check the literal cwd with
  shell metacharacters, interrupt a foreground `sleep` through Ctrl-C, verify
  clipboard/title escape isolation, cancel/accept multiline paste and preserve
  the reviewed clipboard snapshot, then observe child exit. GTK4 launcher tests
  separately verify KzL Agent branding, consent cancellation and stale-project
  guards without starting a real user shell or sending provider requests.
- Active-terminal close regression: cancel leaves shell/job running; confirm
  leaves neither fixture shell nor foreground `sleep` running; a new terminal
  is usable afterward. Closing during async startup leaves no late-running child.
- Process-interruption regression: kill only the owned sandbox GTK client after
  synthetic admission but before its HTTP reply. Restart restores uncertainty
  and the request ID; explicit retry yields one unique fixture admission. Separate
  restarts reconcile visible history without retransmission and preserve edited
  drafts. These are client/protocol checks, not a real model execution claim.
- Gateway-return regression: start against a reserved but non-listening socket,
  restore an authenticated private HTTP fixture, hold a list read across several
  poll ticks and prove no overlapping retries. Restore the saved chat even when
  it is absent from the first history page and its own metadata initially fails.
  Recover catalog/history, preserve draft text/attachments and uncertain IDs,
  preserve edits during a second outage, clear only transient read notices and
  retain unrelated action warnings. An empty-gateway variant stays connected
  without fabricating a conversation. All fixture requests are GETs; writes
  are rejected and counted so automatic retransmission/pairing would fail tests.
- Two actual GStreamer WebRTC peers exchanged nonzero synthetic audio in both
  directions through SDP, ICE, DTLS, SRTP, Opus and SCTP. Captions, context and one
  deduplicated tool proposal passed through the channel; no tool was executed.
  Mute and end released the pipelines. A local output check generated 35 buffers.
  This runs in a private network namespace with one dummy test interface, no
  default route, no public STUN, no host devices and all capabilities dropped
  before executing target code. Critical GObject warnings are fatal in this test.

These checks do **not** prove physical microphone/speaker behavior or a real
OpenAI conversation. Those require user-approved acceptance with separate API
billing. Closing a Live window releases local media; no background-call service
or CallKit integration is claimed. CallKit, physical phone control,
remote interactive shell, automatic folder synchronization, specialized math/diagram rendering and
provider-hosted sandbox attachment download remain outside this release. Activity
review uses native read-only sections. Settings do not alter provider
accounts. Partial model/mode writes report errors instead of claiming atomicity.

Development tests (run inside the isolation described above):

```sh
cd desktop
python3 -W error::ResourceWarning -m unittest -v test_backend test_install test_uploads test_richtext test_terminal_policy
python3 install.py --home /scratch/installed-home
# Start private Xvfb, then use its DISPLAY and a private dbus-run-session:
POCKET_TEST_INSTALL=/scratch/installed-home/.local/share/opencode-pocket-desktop python3 smoke.py
POCKET_TEST_INSTALL=/scratch/installed-home/.local/share/opencode-pocket-desktop python3 smoke_connected.py
POCKET_TEST_INSTALL=/scratch/installed-home/.local/share/opencode-pocket-desktop python3 smoke_download.py
POCKET_TEST_INSTALL=/scratch/installed-home/.local/share/opencode-pocket-desktop python3 smoke_voice_ui.py
POCKET_TEST_INSTALL=/scratch/installed-home/.local/share/opencode-pocket-desktop python3 smoke_upload.py
POCKET_TEST_INSTALL=/scratch/installed-home/.local/share/opencode-pocket-desktop python3 smoke_markdown.py
POCKET_TEST_INSTALL=/scratch/installed-home/.local/share/opencode-pocket-desktop python3 smoke_terminal_ui.py
# Separate process: this imports GTK3/VTE, never GTK4.
POCKET_TEST_INSTALL=/scratch/installed-home/.local/share/opencode-pocket-desktop python3 smoke_terminal.py
POCKET_TEST_INSTALL=/scratch/installed-home/.local/share/opencode-pocket-desktop python3 smoke_terminal_close.py
POCKET_TEST_INSTALL=/scratch/installed-home/.local/share/opencode-pocket-desktop python3 smoke_recovery.py
POCKET_TEST_INSTALL=/scratch/installed-home/.local/share/opencode-pocket-desktop python3 smoke_review_recovery.py
POCKET_TEST_INSTALL=/scratch/installed-home/.local/share/opencode-pocket-desktop python3 smoke_review_recovery.py --kind creation
POCKET_TEST_INSTALL=/scratch/installed-home/.local/share/opencode-pocket-desktop python3 smoke_reconnect.py
POCKET_TEST_INSTALL=/scratch/installed-home/.local/share/opencode-pocket-desktop python3 smoke_reconnect.py --empty
# In a private network namespace with no route outside it, a dummy interface
# at 192.0.2.1/24, and all capabilities dropped before starting Python:
python3 -m unittest -v test_voice
G_DEBUG=fatal-criticals python3 webrtc_smoke.py
```
