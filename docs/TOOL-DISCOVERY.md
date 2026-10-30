# Runtime tool discovery and desktop worker verification — 0.15.1

`plugins/kzl-catalog.mjs` is a read-only OpenCode V2 plugin. It snapshots
`ctx.tool.list()` after runtime transforms, without executing tools, exposing
executors, reading credentials, or modifying permissions. Snapshots are private,
atomic, scoped to the loaded location and expire after 60 seconds. Metadata is
limited to ID, bounded description and argument names, not schema defaults.

Install locally by loading the plugin through OpenCode's supported plugin
configuration or a local shim. The current notebook uses a small global shim
which re-exports this module. Do not copy the owner's absolute path to another
machine. The repo contains no credentials or private session IDs.

`GET /phone/kzl/capabilities?q=linux_computer` returns up to 30 matching tools.
`available`, `matching`, `total`, `complete` and `checkedAt` distinguish real
inventory from missing/stale data. An inventory entry is not an authorization or
proof the underlying application is reachable. The executor retains normal
permission evaluation. Realtime treats descriptions as untrusted data.

## Desktop coordinator execution

The `computer-use` primary agent delegates visual work to `computer-use-luna`.
It intentionally cannot invoke desktop tools directly. Nesting a task under KzL
consumed the allowed subagent level, so root KzL desktop tasks now create an
independent executor session with `kzlParent` metadata. Existing explicit session
permissions, model and agent are copied; global depth limits are not changed.
Nested KzL parents do not use this shortcut because ancestor rules may apply.

Read-only end-to-end test on 2026-10-30 confirmed:

- coordinator model `gpt-6.1-terra-fast`;
- one delegated worker with model `gpt-6.1-terra-fast`;
- actual `linux_computer_apps` tool event with `completed` state;
- returned `DESKTOP_READ_OK`.

No click, typing, screenshot, file reading or application change was requested.
This validates discovery and one read-only delegation, not full desktop workflows
or iPhone audio/keyboard behavior. Physical testing remains required.

## Delegated activity (0.15.2)

The activity endpoint traverses verified Core parent links (maximum 3 levels and
20 sessions) and projects recorded worker tool steps, not only coordinator steps.
Each step carries its source session ID. Screenshot requests recheck that source
against task ancestry before reading the message. Foreign sessions and forged
parent links are rejected; no client-provided path or URL is fetched.

Fixture tests cover delegated inline screenshots and cross-task rejection. The
live gateway found the completed `linux_computer_apps` step in the actual Terra
Fast worker session from the read-only integration test. That test generated no
screenshots, so physical capture/rendering remains unverified. The bounded recent
page is not an exhaustive export of every historical action.
