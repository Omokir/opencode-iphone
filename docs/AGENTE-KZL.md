# Agente KzL — 0.11.0

## Experience

Agente KzL has a permanent entry above the ordinary conversation list. Its
identity is stored on the notebook, not recreated when a call ends or the app
updates. A missing session produces an error; the app never silently substitutes
a new empty session. Existing unrelated chats are not migrated or deleted.

Use the chat for text or tap the phone to talk to OpenAI Realtime. Voice calls
from other conversations also use this permanent agent, not the selected
conversation's execution context. The call screen identifies this explicitly.

Clear voice requests are delegated without the old extra visual approval and
without local biometric authentication for each delegation. Existing OpenCode
permissions, agent mode, provider authentication and OS protections remain in
force. This does not grant root access or enable passwordless sudo.

## Execution and results

The authenticated gateway owns a durable SQLite task ledger under its private
state directory. A task is recorded before an execution attempt and receives
separate task, child-session and prompt IDs. It inherits the permanent session's
location, model and agent; Plan is not silently changed to Build.

Realtime gets an immediate queue receipt, not a fabricated execution result.
The coordinator executes work in child sessions, monitors results and returns
updates to the active call. Work in the same workspace is serialized, with up
to four unresolved tasks. A new request can queue while conversation continues.
Explicit corrections use the task ID and OpenCode's `steer` delivery.

OpenCode events wake reconciliation, with periodic reads covering missed events
and reconnects. Core event subscriptions have no replay. The iPhone receives
task revision hints over an authenticated SSE endpoint and reconciles state;
it is not responsible for keeping the agent alive.

Task IDs and dedicated child sessions prevent unrelated parent-chat answers
from being reported as results. Uncertain writes are never automatically
replayed. An unresolved admission blocks subsequent queued execution until it
can be reconciled or explicitly interrupted. Interruption cannot undo changes.

Ending a call or interrupting speech does not cancel notebook work. During a
call, open an individual task to answer its permissions/questions (the mic is
muted when opening review). Outside a call, use **Tarefas e histórico de voz**
in the permanent chat. Results and recent voice text also appear in its timeline.

## Memory and privacy

The app does not record audio. User speech transcription uses
`gpt-4o-mini-transcribe`, which can add API cost. Confirmed text turns are saved
in the private notebook ledger. Transcripts can be inaccurate or contain
interrupted assistant speech. Do not dictate passwords, keys or 2FA codes.

Voice text and task results are also mirrored into Core as historical synthetic
context with `resume: false`; this never starts an agent run by itself. An
uncertain mirror is not retried blindly; durable originals remain in the ledger.
The recent transcript is available in the app and its protected offline cache.

Each new call receives bounded recent text and task summaries. This is persistent
history, not unlimited model memory. Older text is retained, not automatically
deleted. The current activity screen shows the latest 100 voice turns and tasks.
Storage limits fail explicitly instead of dropping history silently.

## Capabilities

Realtime can query a sanitized, location-scoped MCP connection list and visible
agent names. No configuration, system prompts, environment variables, headers,
credentials or raw connection errors are exposed. A connected MCP is **not** a
guarantee that every tool is available or allowed. This version does not expose
a complete tool-schema catalog. OpenCode retains its normal tool discovery and
server instructions and chooses tools during execution.

Context, catalog descriptions and tool results are data, not new authorization.
Publishing, sending messages, purchases, destructive operations and privileged
actions retain applicable protections. Permissions are never auto-approved by
the voice coordinator.

## Transport limitation

Audio remains native WebRTC, brokered through OpenCode with the API key staying
on the notebook. The current public broker response exposes SDP but no call ID
for attaching a Realtime sideband. This version therefore forwards tool calls
through the iPhone data channel to the persistent notebook coordinator. It does
not implement GPT-Live, and it does not claim native Realtime sideband support.

If the phone disconnects, execution continues but live spoken updates stop.
Reopening a call loads task state instead of resubmitting tasks. The call still
ends when iOS backgrounds the app. Tailscale and an awake notebook remain required.

## Validation

Fixture tests cover permanent identity, restart, duplicate requests, uncertain
admission, workspace serialization, cancellation, exact-result association,
context persistence and sanitized capabilities. Native tests validate strict
tool arguments and complete-item dispatch. Builds do not start paid calls or
capture a microphone. End-to-end latency, audio interruption and delegated work
must be tested on a physical iPhone after installation.
