# iPhone control — 0.3.0

The Pocket app remains a client of the notebook. Physical iPhone control uses
the local MCP, a signed Device Kit XCTest agent and compatible developer image.
No remote-fleet reservation, jailbreak or background iOS daemon is installed.

## Consent boundary

- Panel explicitly enables screen reading for 15 minutes. Lock state is unknown,
  not guessed from USB presence. Current test transport is USB, unlocked phone.
- A dedicated conversation uses an isolated Git workspace and explicit permission
  rules: other tools denied, read-only iPhone tools allowed, every mutating iPhone
  tool asks, mixed batches and remote-fleet/install tools denied.
- The app offers only allow-once or reject for this conversation. It shows tool
  arguments before approval. If arguments cannot be retrieved, allow is disabled.
- Stop writes disabled state first, then requests conversation interruption and
  stops the action daemon. The normal MCP path checks state before each device
  command, so later tool calls cannot automatically restart automation.
- Already-performed actions cannot be undone. An action in flight may finish.
  If notebook/VPN is unreachable, app cannot confirm Stop: lock phone or remove
  cable. Nothing silently replays a failed write or prompt.

This is not a sandbox against processes with the notebook user's filesystem or
shell authority. Other existing chats retain their own permission rules. Never
claim semantic detection of whether a tap means navigation, send, delete or buy:
every mutating action requires explicit approval in the dedicated conversation.

## Host integration

`~/.local/state/opencode-iphone/automation-config.json` (mode 0600) defines local
paths `cli`, `home`, `workspace` and the authorized physical `deviceID`. It contains
no Apple password or provider credential. Workspace must be a separate empty Git
repository, not an existing project with saved approvals.

MCP env:

```text
MOBILECLI_PATH=<local iOS compatibility helper>
MOBILECLI_HOME=<action daemon directory>
MOBILECLI_CONTROL_STATE=~/.local/state/opencode-iphone/automation.json
```

Use an expanded absolute path for state. The helper's `CheckAutomationGate`
rejects missing, invalid, disabled or expired state. Host metadata calls use a
different daemon directory (`<home>-metadata`) to avoid accidentally starting an
ungated action daemon. Stop targets only the action daemon.

The local helper preserves the original npm binary. It is built with
`-tags iosreal_local`, explicitly rejects non-physical-iOS targets, recognizes
iLoader's Apple-team suffix and includes gate regression tests. Rebuild it after
updating code and stop any older action daemon before enabling the gate env.

## Signing/runtime evidence

Device Kit 0.0.35 original IPA SHA-256:
`40e72380fcb89b2fd71edf7d2766e75c3676e4938af2393db92aecd2b101c46d`.
`scripts/prepare-device-agent.py` preserves executable bytes and original IPA;
adapts XCTest identifier metadata for iLoader. iLoader 2.4 re-signs nested test
bundles, unlike the previous signing path. Apple credentials stay in iLoader.

The old automatically-downloaded developer image caused a missing XCTest symbol.
The replacement manifest and payload hashes were verified before mount. After
reboot the developer image may require mounting again; signing also expires.
Installation is not evidence that runtime is ready: verify a screen read and a
harmless tap separately. Do not inspect unrelated photos, files or app content
while diagnosing.

## Verification

- `python3 -m unittest discover -s bridge -v`
- Native model tests and device build in GitHub Actions.
- Simulator fixtures use `SNAPSHOT`, excluded from device IPA.
- Runtime: start, confirm a harmless navigation action, Stop, verify gate denies
  later commands. Never send/delete/purchase merely to test controls.
