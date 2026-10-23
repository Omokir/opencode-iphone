# 0.6.0 — daily-use improvements

## History and reconnect

Successful session-list, session-info and initial message reads have a private
offline cache (4 MiB/item, 80 files, 32 MiB total, oldest written entries evicted).
Permissions/forms, configuration, device tokens, searches and cursor pages are
never cached. Cached history is informational: it never authorizes actions or
replays sends. Files use complete iOS protection, are excluded from backup, and
are hashed by server/path. Settings can clear owned cache files without touching
drafts or inbox originals. Recent history appears while network refresh runs.
Older history may still need notebook connection. Cache retention means chat
content is stored locally; enabling app lock is recommended for shared devices.

DNS, offline, refused connection, timeout and dropped connection have separate
guidance, not a claim that Tailscale state was directly measured. Read-only
foreground polling reconnects; uncertain prompts remain manual. A saved reading
position is restored if its message is among loaded history. Returning to latest
clears that bookmark. Search inside chat searches loaded messages only; load
previous messages to extend its scope.

## Home and chat

Notebook indicators are collapsed by default; chat filters and pinned chats are
visible without scrolling through storage/quota panels. Extra tools are in the
top menu. Filters use notebook session metadata, not push/background presence.
Message rendering supports fenced code with explicit Copy, basic pipe tables,
inline Markdown, copy-message menu, and expandable tool cards. Tool previews are
bounded textual output, not arbitrary binary attachments or an interactive shell.
Unsupported Markdown remains readable text. Full details stay on notebook.

## Inbox transfer queue

Inbox uses acknowledged 4 MiB chunks and consults server's actual staged size
before resuming. Chunk SHA-256, immutable upload ID/path/size/full checksum and
non-clobber final commit prevent accidental overwrite. Commit checks full file
checksum, then phone separately reads server verification of actual destination
bytes before any local removal. Retries do not assume a lost response failed.
Progress shows acknowledged bytes and average newly-transferred bytes/sec, not
an estimate of final verification time. Empty files are supported. Resumable
uploads currently cap at 1 TiB and require space for partial and final temporary
copies plus reserve. Partial files survive restart; they are not age-deleted.

Pause stops admission at chunk boundaries; in-flight chunk/verification/commit
can finish. An error pauses queue for explicit resumption. Original stays local
on failure/uncertainty. No background execution guarantee. Switching server,
disabling or cancellation prevents subsequent local removal; a removal already
admitted is not undoable. Files changing during transfer fail checksum or the
local coordinated unchanged check.

Copy mode preserves local originals and records copied content hashes to avoid
repeated upload of the same bytes. Changing contents creates a new transfer.
Switching to move mode does NOT retroactively delete copies previously retained.
New installations default to copy; existing enabled move installations preserve
their established choice. Enabling deletion requires visible confirmation.
Local verified-transfer history keeps last 100 records, with private file
protection and backup exclusion; it contains names/destinations but no bytes.
History persistence is best effort, never used as proof of remote file contents.

## App lock and devices

Optional Face ID/device passcode uses LocalAuthentication. Unlock required on
return from background; sensitive confirmations also request user presence when
enabled. Stop is never gated behind another biometric prompt. This is an app UI
lock, not a new encryption scheme or a block against OS screenshots, jailbroken
devices or notebook-user access. It does not turn Pocket into a remote iOS agent.

New pairings issue separate 48-byte random device tokens. Server stores SHA-256
hashes and labels, never clear tokens in registry/list responses. Existing shared
token remains explicitly listed as legacy until revoked; revoking it invalidates
all old clients/integrations, not one old phone. Pair again to obtain independent
tokens. Any trusted paired client can revoke paired access, so pair trusted
devices only. Already admitted operations can finish; existing SSE connection
may remain until bounded reconnect. Local Disconnect is not server revocation.

Diagnostics share only app/iOS versions and coarse connectivity flags, not
server URL, tokens, IDs, chat or filenames. Public-code version check contacts
GitHub only on request; source version is not proof of a published, approved or
signed IPA. App does not silently download/install updates. Experimental local
agent probe is hidden by default behind Settings advanced toggle. USB control
remains the only physically demonstrated automation path.

## Verification

Python tests cover independent token revocation, redaction, wire API, chunk
resume after restart, replay/conflict, incomplete commit, bad checksum and
preservation of desktop changes. Native policy tests cover cache route scope,
server-key isolation and connection advice. Device build and physical acceptance
are separate stages; no claim of simulator interaction when that stage is skipped.
