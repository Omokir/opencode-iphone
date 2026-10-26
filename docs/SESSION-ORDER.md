# Session activity order — 0.9.1

History uses Core's shared session activity: `time.updated DESC`, then `id DESC`.
It does not sort by creation, local opening/read time or server `time.viewed`.
Sending/receiving activity on either client is reflected by refreshed Core metadata.
Opening a chat on phone does not synthesize activity or alter desktop read markers.

Core already returns the right order. Native pagination used append-and-skip for
duplicate IDs and retained previously-loaded records without canonical sorting.
Now merge replaces duplicate IDs with incoming metadata and reorders all loaded
sessions. Search and offline cache display apply the same comparator. Pinned
section retains user's existing per-phone pin ordering; unpinned history mirrors
server activity. Unpinning returns a chat to its activity rank, not append order.

Refresh polls while list is foreground and reloads when returning from a chat.
Newest page is refreshed; older retained pages have last-observed metadata until
queried again. Current activity naturally moves a chat into newest server page.
Offline uses last-observed state and cannot claim live computer synchronization.
There is no guaranteed polling while iOS suspends the app. Changes of server or
pairing invalidate in-flight page results.

Reference verified against OpenCode V2 `dev` source:
`packages/core/src/session/store.ts` selects `SessionTable.time_updated`, then ID;
`packages/tui/src/component/dialog-session-list.tsx` requests descending session
list and keeps server order after separating local pins. Live local API's first
100 root sessions were descending by updated, but not created/viewed.

Regression tests cover old-created/recently-active chats, ignoring viewed time,
ID ties, duplicate pagination and fresh metadata replacement. No desktop
configuration, conversation contents, pins or read state are rewritten.
