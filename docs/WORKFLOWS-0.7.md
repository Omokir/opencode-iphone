# 0.7.0 — projects, history and system integration

## Projects

Conversation list → top menu → **Projetos favoritos**. Save absolute notebook
folder and display name; tap favorite to create conversation without sending a
prompt. Chat menu → **Favoritar projeto** saves current folder. Favorites are
local, scoped per server, deduplicated by trimmed path, limited to 30; removing
favorite does not remove any notebook directory. Server validates actual new
session location. Uncertain creation is never automatically repeated.

## Search entire chat history

Chat menu → **Buscar no histórico completo**. Unlike loaded-message search,
this calls notebook gateway, which searches actual paginated Core message pages.
Core currently supplies no text-search parameter on message history. Gateway
therefore scans one 15-message page per request, propagating opaque cursor, with
two concurrent search slots. Queries are 1–200 characters; matching is normalized
Unicode/case-insensitive. Only user/assistant text is searched, not tool output,
attachment bytes or PDFs. Result excerpts are bounded; tap to fetch full message.

App scans up to 100 pages per batch, showing scanned count/results. If history
continues, explicit Continue scans next batch until cursor ends; no silent
"complete" claim at batch limit. Closing or editing search invalidates old
responses. Needs notebook connection. No query/index persisted on notebook.

## Optional notifications — local, NOT APNs push

Settings → **Notificações opcionais** requests iOS authorization only on opt-in.
Generic alerts contain no chat names, filenames, screen data or message content.
Observe completed sessions during foreground list refresh; observe permissions
in the open chat; background upload can announce server receipt separately.
Event keys are hashed for bounded deduplication. Disabling removes app's pending
and delivered notifications.

These are NOT remote push notifications. When app is suspended, it does not keep
polling notebook; new notebook events may be observed only on return. No fake
background audio/location execution. Real APNs requires appropriate provisioning,
push entitlement, server credentials and provider integration, not configured
by this build. Notification permission alone does not enable APNs.

## Open in Pocket — Files/document receiver

App declares `public.item` as an alternate document handler and receives file
URLs through SwiftUI openURL. In apps offering **Open In / Copy to**, select
Pocket, unlock if needed, then confirm copying into **Iphone 11 Omoki**. Up to
64 MiB per import; regular files only, no archive extraction. Provider source is
never removed. If inbox automatic transfer is active, imported copy follows its
already-selected copy/move policy. UI explicitly discloses this before import.

This is NOT a Share Extension. It does not guarantee Pocket appears in every
share sheet or receives a Photos item directly. A proper extension supporting
Photos needs a separate signed executable and a valid shared-container approach;
current free signing/ReuseMain setup is not validated for that. No extension,
private entitlement or launcher workaround is silently bundled. That portion of
requested integration remains pending compatible signing and physical testing.

## Optional background upload

Inbox panel → **Continuar envio iniciado em segundo plano**. Default off.
When enabled, files up to 64 MiB get an immutable staged copy and a background
URLSession upload task to the same paired HTTPS notebook endpoint. Bigger files
keep foreground chunked resume. Scheduling requires space for extra local copies.
The OS may defer transfer; Tailscale must stay connected. User force-quit cancels
background transfers; only system termination has automatic wake/reassociation.
This does not monitor new files indefinitely when app is closed.

Staging body and task metadata are excluded from backup and protected until first
user authentication, so iOS can read staging after phone subsequently locks.
This is deliberately different from fully-locked-access protection on originals.
User enables this policy explicitly in panel. No bearer token is stored in our
job manifest; system URLSession manages its own request headers and credentials.

Persist upload identity before resume; match task identifier and receipt's ID,
root, path, size and SHA-256. Maintain bounded response buffers. A backend receipt
is only acknowledgement, NOT proof for deleting original. Delegate never removes
originals, never runs UI actions, and never follows up with automatic deletion.
On next foreground sync, existing actual-content verification and unchanged-file
check must pass before the user's move policy may remove local original.

Pause/cancel requests cancellation and pauses new admissions; already received
bytes/commits may finish. Disabling background pauses queue; explicitly resume
to continue in foreground. Disconnect cancels system tasks. On reassociation,
unknown, unapproved/server-mismatched or suspended orphan tasks are cancelled.
Records and staging cannot be cleared while corresponding OS task is active.
Uncertain outcomes preserve original; server non-clobber/checksum/receipt behavior
prevents overwriting a conflicting destination on OS retries.

## Verification boundary

Python tests cover older-page search, opaque cursor propagation, Unicode and
exclusion of binary/tool contents, alongside existing file/security tests. Native
tests cover favorite persistence/isolation/deduplication and strict receipt match.
Build does not establish physical background completion, notification delivery
or presence in third-party document menus. Those require device acceptance after
update, separately from compilation. Simulator UI stage may be skipped by user.
