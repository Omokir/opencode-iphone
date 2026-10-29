# Chat history and tail following — 0.12.1

## History on open

Opening a chat synchronously hydrates its protected cache. Foreground loading
requests the history page before auxiliary metadata, permissions and forms.
History becomes readable even if those detail requests fail. Failed history
reads preserve saved text and expose an explicit read-only retry.

History and streaming responses merge by message ID and request revision. A
newer assistant-only page cannot reject missing older messages from an in-flight
full history page. Conversely, a late full page cannot overwrite newer streamed
text. Older cursor pages only add missing messages. Pagination is preserved.

Requests are bound to server, connection generation and session identity. Late
responses from a previous pairing or cancelled view cannot populate a new one.
Loading restarts on foreground entry and connection changes, independent of SSE
events and independent of sending a message. No write or prompt is used to refresh.

## Latest messages during execution

Tail following is explicit user intent. The Latest button clears the old top
anchor and resumes following. Programmatic scrolling, residual deceleration and
stale geometry cannot turn that intent off. An actual manual drag pauses it
again; tapping Latest resumes it. A touch without movement only pauses scrolling
until release. This also works with the iOS 17 gesture fallback.

Reading position uses the top-ID binding only while reading. Following uses the
bottom scroll command, after view updates, and re-aligns on actual stack or
viewport layout changes (including growing responses and keyboard resize).
The full stack is measured instead of depending on a lazy final row. A saved
reading position is restored when its message is in the loaded page; messages
outside that page remain available through existing cursor pagination.

## Verification boundaries

Native tests link the real ChatStore to a fixture transport: metadata failure,
pending-endpoint failure, offline cache, deliberately reordered full/streaming
responses and pairing changes. Pure scroll-policy tests exercise reading,
following, inertia, saved anchors and explicit Latest intent. They do not send
network requests, prompts, voice calls or permissions.

The first 0.12.1 CI run also runs the history fixture against the unchanged
0.12.0 parent to verify that the original defects fail the same assertions.
Physical layout, long streaming answers, keyboard changes and scroll gestures
still need validation on the iPhone; policy tests do not prove rendered UI.
