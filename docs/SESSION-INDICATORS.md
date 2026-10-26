# Shared reads and running indicator — 0.9.2

## Blue means a completed response not yet observed read

Core Session.Info.time.viewed is the shared read timestamp set by computer's
OpenCode. Phone compares completion time.idle with maximum of initial baseline,
local read marker and shared viewed marker. Viewed >= completion clears blue;
read before a new completion does not hide that new result. No iPhone wall clock
or inferred reading is used. Missing/failed markers never mean read.

Fresh session pages and search DTOs decode viewed. Normal foreground refresh also
queries metadata-only batches for loaded older/pinned records not in newest page,
up to 120 per batch with rotation for longer loaded lists. Gateway validates IDs,
limits body/concurrency and projects only viewed timestamps. Core is queried with
GET only; no /view writes, chat content or global configuration forwarded. There
is no push/background synchronization guarantee. Offline remains last-observed.

Local read state remains per iPhone/server, but a read confirmed by computer now
also clears the phone marker. This change does not write phone reads back to
computer or synchronize per-device pins.

## Green means server-confirmed running

GET /api/session/active returns IDs whose foreground session drain is running in
the same Core process. No result or missing outcome is NOT used as a proxy for
running. Root sessions are green only when their own ID is active; this is not
an assertion that every background tool/process or active child is represented.

List fetches active state concurrently with metadata. Green takes precedence over
blue and pulses with native SwiftUI symbol effect. Reduce Motion leaves green
solid; VoiceOver says running rather than relying on color. Snapshot expires ten
seconds after successful response and clears on background/failure; unknown is
shown as unknown, not a cached green indicator. Active endpoint is excluded from
history cache. Running filter now uses same authoritative active IDs.

API availability depends on Core version. If active/read lookup is unavailable,
history still loads but no synthetic running state is created. This client does
not start sessions, authorize tools, mark sessions read or change their ordering
to render indicators.

## Verification

Native tests: desktop read, older cached DTO plus marker batch, later completion,
server isolation, baseline not lowered by old viewed value, active empty/running
decoding and cache exclusion. Python tests: authentication, read-only proxy,
metadata projection, ID/body limits, deduplication, unavailable/malformed markers.
Physical pulse/read refresh acceptance remains separate from IPA compilation.
