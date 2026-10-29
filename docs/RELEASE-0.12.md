# Pocket 0.12 — conversation-first interface

Native split navigation places history in the sidebar and conversation in the
detail. iPhone collapses these columns; iPad can show both. Chat uses open
assistant responses, quieter user bubbles, grouped tool disclosures and a
rounded multiline composer with attachment/actions menu and voice button.
Voice controls retain existing KzL behavior, including persistent task and
transcript semantics; visual changes do not change consent or execution policy.

Core 2.2.1 actions are loaded for the selected project: commands, skills,
pending inbox and per-session schedules. Unsupported or failed reads show an
unavailable label, not synthetic state. Commands and skill activation are
explicit user actions; writes are never retried. Unknown write outcome locks
the action panel until closed and reviewed. Schedules need Core's existing
experimental configuration; Pocket does not enable it automatically.

Inbox API cannot edit message text. This version offers cancellation only,
and does not claim already-delivered work was undone. Scheduling supports a
single dated execution, plus pause/resume/delete of existing schedules.

Activity centralizes approvals/questions for all sessions in a selected
project. Core scopes these endpoints by location; the UI does not claim a
global cross-project inventory. Opening an item loads its original session.

Pending follow-up: dedicated rich diff/terminal
views, recurring-schedule creation, device screenshots and acoustic voice
acceptance. Existing per-conversation approvals and KzL tasks remain available.
Compilation does not establish physical visual/audio acceptance.
