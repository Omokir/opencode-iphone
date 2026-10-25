# 0.9.0 — observability, recovery and notebook power

## Voice: clearer, not a claimed acoustic fix

Connection-without-sound has not been reproduced with user's paid API/microphone.
Existing no-API local tone and private diagnostics remain. Add input level,
current output type/system volume, system audio route picker and an explicit
speaker request that refuses to remove external headphones automatically.
Bluetooth/route changes can still end call; restart is manual. No paid testing,
key reading, microphone capture or volume override is performed by development.

Call timer uses monotonic clock. Limit defaults to 5 minutes, configurable 1–15,
captured when call starts; wall-clock edits do not extend the deadline. Output
budget defaults to existing 512 tokens; explicit 1024/2048 choices warn of cost
and are not silently selected to hide failed/incomplete voice responses.

Realtime usage is aggregated only from response.done usage objects, deduplicated
by response ID. Missing data remains unknown, audio counts identify coverage,
cached/audio tokens are not added twice to totals. Counts are observed partial
usage, not invoice, remaining balance, currency estimate or monetary cap. Lost
final events can leave last turn unreported. Usage stays in memory, not logs.

## Task history and response association

Typed and voice prompts persist identity before submission, with bounded title,
server hash, session ID, generated request message ID, date and lifecycle state.
Archive is private, fully protected and excluded from backup, at most 100 records.
It contains task-title text and IDs; unlike diagnostic sharing, this is local
user content. Storage failure before new submission blocks that submission.
Crash/voice termination leaves uncertain state, never automatic resend.

Actual recent page must contain original user message. Completed assistant reply
must be in that user's window, before next user message; later client's response
is not substituted. Insufficient/ambiguous history remains uncertain. Full reply
is linked by message ID; latest-chat summary is not used for a task-specific
result when explicit result ID is known. This is conversational association, not
proof of every desired filesystem/command effect. Existing backend operation
permissions remain intact. Read-only refresh/open-result actions do not replay
the prompt. Old tasks outside recent page may require manual chat inspection.

## Unified transfer center

Top menu or Settings → **Central de transferências**. Shows manual sends/downloads,
current inbox queue, OS background tasks, and verified inbox history together,
scoped by server. Background jobs already represented by verified inbox history
are suppressed as duplicates. Manual progress observes actual URLSession task
byte counts tagged with native transfer UUID, not elapsed-time estimates.
Network completion is separate from checksum/verification; downloads are private
cache, not promised saved to Files. Manual ambiguous uploads can read a matching
receipt without replay; receipt alone does not prove current remote bytes.

Manual activity metadata is privately archived, at most 100 records. Relaunch
marks unfinished manual entries uncertain; there is no persisted write-retry job.
Manual staging is bound to server and connection generation; disconnect cancels
only old-generation URLSession requests, not a new pairing request. An old manual
proposal cannot resume against another server or newly paired connection.
Cancel requests cancellation; a commit may already have arrived. Automatic queue
resumption uses existing checksum/receipt safeguards. Pausing persists and keeps
originals; no blanket delete/reset action was added to the center.

## Updates

Settings → **Diagnóstico e atualização** queries public GitHub only when requested,
rate-limited locally to once/minute. Ready requires workflow status completed,
conclusion success, expected non-expired artifact, and matching artifact/run SHA.
Version/build come from Info.plist at successful run's immutable SHA, not main branch.
Links point to that build and its README/notes. Source-only changes are not called
ready. Build success is not physical-device validation. GitHub login may be
needed to download artifact; app never downloads/signs/installs silently and does
not send notebook/OpenAI tokens to GitHub. Public rate limits can block lookup.

## Notebook power

Settings → **Energia · desligar notebook** checks login1.CanPowerOff without changing
permissions. Only Linux's noninteractive yes capability enables preparation.
User types DESLIGAR, completes optional device authentication, then gives final
confirmation. Gateway issues credential-bound 45-second one-shot memory ticket;
power-off consumes it before invocation. Legacy shared credentials still share
identity. API consent flags are not proof of human action; pair trusted devices.

Command is fixed `systemctl --no-ask-password --no-block poweroff`. No arbitrary
shell, Polkit changes, root grants, inhibitor bypass, scheduled hidden shutdown,
automatic retries or voice power tool. Response means admission, not physical
power state; connection may vanish before response. Work/transfers can be
interrupted and other apps might have unsaved data. Do not use until user saved
work. Tests inject fake subprocess; no real poweroff is executed in verification.

**Power-on remains unavailable:** powered-off notebook cannot run Tailscale or
receive app calls. Wake-on-LAN needs compatible BIOS/NIC/power/network and another
always-on device on notebook's LAN (or equivalent infrastructure) to send wake.
No relay/hardware configuration is assumed or silently installed. UI explicitly
disables unavailable wake rather than promising it. Keep-awake is not power-on.

## Acceptance pending

Native/Python policy and archive tests plus IPA compilation are automated.
Actual audio, route controls, OS background behavior and shutdown/wake physical
behavior require separate owner-attended acceptance; development does not execute
paid voice calls or turn off the machine to claim completion.
