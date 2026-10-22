# Files, drafts and live chat — 0.4.0

## Notebook browser

Open the folder icon on conversation list, or **… → Arquivos do projeto** in a
chat. Default root is notebook home only. Additional roots require a trusted
notebook-side `~/.local/state/opencode-iphone/file-browser.json` configuration;
the phone cannot expand its own authority.

No delete, shell execution, archive extraction or folder creation API is exposed.
Hidden paths and common key/credential formats are blocked, and links/special
files are not followed. Uploaded bytes may still be interpreted by other
programs running on notebook; this is file access as the notebook user, not an
isolation boundary against that user or a malware scanner.

Every client-supplied path component is traversed using directory descriptors
and `O_NOFOLLOW`; absolute paths, traversal and symlink escapes are rejected.
Files are bounded to 64 MiB per transfer. Listings return up to 2000 entries and
explicitly disclose truncation. Downloads use a bounded private snapshot and
SHA-256 verification. Save/Share exports from protected app cache into iOS Files.

Uploads stage immutable private copies on iPhone, send raw bytes with SHA-256,
and commit a temporary sibling only after all bytes/checksum match. New files
use no-clobber creation; replacements require explicit UI confirmation plus the
version observed by the client. Version is rechecked before commit. This catches
concurrent app uploads and detected desktop changes, but is not a serializable
transaction against unrelated desktop programs racing the last filesystem step.

Upload IDs have private receipts so uncertain responses can be checked without
replaying writes. Absence of receipt is not proof that nothing was written: if
commit succeeded but receipt persistence failed, inspect folder manually.
Cancel does not promise to undo a commit already received by notebook. Keep app
open during transfers; no background-transfer guarantee is made.

## Drafts and previews

Text and up to five existing chat attachments persist in per-server/session
draft scopes. iOS files use complete file protection and are excluded from
backup. No draft is sent automatically. An uncertain-send flag survives restore
and instructs user to inspect chat before manual retry. Empty/successfully sent
drafts are cleared only after acknowledged submission and UI content updates.
If storage/protection prevents save, UI says draft was not saved.

Pending image chips use bounded thumbnails. Tap an attachment for native Quick
Look and explicit Share/Save. Preview does not upload the file to notebook.

## Live updates and mode fix

Core SSE is reduced to session-specific change hints; other chat content is not
forwarded. Native client coalesces changes, refreshes small assistant pages and
reconciles history after reconnect. Periodic read-only refresh remains fallback;
writes/prompts are never silently retried. Inline attachment base64 is omitted
from mobile history projections rather than resent on every update.

The Plan/Build defect came from Session equality comparing only ID. Equality now
includes decoded metadata so SwiftUI notices a mode/title/model change. A mode
write is confirmed with a fresh session read; failures remain visible. Revision
checks prevent older refreshes from reverting confirmed mode state.

On current iOS, scrolling pauses automatic following while user reads older
messages; an explicit “Últimas mensagens” control resumes following. Background
iOS suspension still pauses live UI updates. No push notification is implied.
