# KzL Center implementation status

Work branch: `feat/kzl-center`, based on `codex/kzl-desktop-redesign`.
The original worktree and its unpublished mobile changes are not modified.

## Implemented in source

- Authenticated, read-only `/phone/connections?directory=...` inventory.
- Location-scoped MCP status and integration authentication-method metadata.
- No configuration, credential records, raw errors, OAuth URLs or method forms
  are forwarded to clients. Independent category failures are explicit.
- Native Linux settings entry and native SwiftUI conversation-resources entry.
- Separate private persistent MCP declaration registry, atomic writes, revision
  conflicts and explicit canonical project grants; default access is empty.
- Registry operations never spawn commands, contact MCP URLs or change OpenCode
  configuration. Registration is not runtime activation or a tool permission.
- Authenticated registry GET/POST endpoint with optimistic revision checks.
- Linux add/grant/revoke/remove forms with explicit confirmation, frozen payloads
  and uncertain-write fencing until manual read-back.
- OpenCode MCP transform adapter (`plugins/kzl-connections.mjs`), applying exact
  project grants under `kzl_center_`, reconciling declarations every two seconds.
  Unrelated MCPs are preserved; pre-existing conflicting names are not replaced.
  Missing/invalid state removes adapter-managed connections on reconciliation.
- Native Pocket MCP registration/grant/revoke/removal view, frozen confirmation
  payloads, selected-computer/project fencing and pending-write bit persistence.
  An uncertain write requires a fresh read plus explicit acknowledgement before
  another write. Pairing/Keychain code is unchanged. Swift tests are added but
  have not been compiled or executed on this Linux host.

## Not delivered yet

- Native iPhone compilation/installation and real-device UI validation.
- iPhone provider account UI, activation/selection of passive API credentials,
  and real-account authorization (requires the owner). Linux registration uses
  OpenCode's existing credential store, not a second gateway secret store.
- iOS build/sign/install, screenshots and end-to-end tests on the owner's actual
  iPhone. The Linux deployment is recorded below.
- VPS central/local executor separation; no VPS deployment was requested yet.

OpenCode MCP experimental add/remove endpoints are runtime overrides, not durable
configuration. Do not use their success response as evidence of persistence.
Project grants are declarations until the adapter is installed and runtime state
is read back. A persisted revocation is not proof of disconnection, and cannot
cancel already admitted tool operations. Existing OpenCode permissions and the
gateway's sensitive-action restrictions remain unchanged. The adapter does not
grant blanket tool permissions or override existing permission rules.

## Validation

Run bridge unit/wire tests inside an isolated namespace with read-only source,
empty environment, private temporary HOME, no external network, and resource
limits. Wire fixtures use only the namespace's loopback and dummy tokens. Do not
run this suite against the live gateway or expose real credentials to tests.

Physical-device discovery returned no available local device during this session.
An iPhone must be connected, unlocked and trusted for the real-device acceptance
test. A successful unsigned IPA build is not evidence of signing or installation.

Latest isolated checks: 49 Python inventory/registry/gateway tests and seven Node
adapter tests passed. These establish persistence, exact-project projection,
authentication, conflict handling and configuration reconciliation in fixtures;
they do not establish real MCP tool execution or iOS compilation.

Additional runtime test (`tests/mcp_runtime.py`) passed with the installed OpenCode
2.2.7 binary in an OS sandbox and a real local stdio MCP fixture: project-scoped
connection, no tool execution at registration, explicit rejection causing zero
tool calls, allow-once causing exactly one call, disconnection after revocation,
and zero additional calls for a subsequent synthetic model request. Its model
provider is loopback-only and synthetic; no real account, paid API or user service
is accessed. The plugin must be configured as directory
`plugins/kzl-connections`, not the standalone `.mjs` file.

Native model tests, on a macOS toolchain and inside an offline execution sandbox:

```sh
xcrun swiftc -parse-as-library -framework CryptoKit ios/MCPRegistry.swift tests/MCPRegistryTests.swift -o "$SCRATCH/mcp-registry-test"
"$SCRATCH/mcp-registry-test"
```

This test does not compile SwiftUI views or replace real iPhone validation.

## Consolidated branch validation blocker

The two changes from `ios-voice-0.17.1` (`e47c1a3`, `bc94613`) are reconciled:
Live capability discovery and confirmed session/project binding are preserved.
The consolidated iOS source version is 0.18.0/build 34; it is not an IPA release.
All 130 bridge tests passed in a Linux namespace with no external network,
private temporary HOME, read-only source, cgroup CPU/memory/process limits,
128 MiB per-file limit, 256 MiB writable tmpfs and a 90-second deadline.

Native verification was attempted in three macOS jobs. Runner refused
RLIMIT_AS, RLIMIT_DATA and finally the soft resident-set policy with
`ulimit: ... cannot modify limit: Invalid argument`. Most recent evidence:
https://github.com/Omokir/opencode-iphone/actions/runs/42917186675

No target Swift compilation/test execution occurred in these jobs. The memory
gate remains fail-closed; compilation must use an execution environment with
enforceable resource isolation. Automatic push triggering is disabled to avoid
repeating blocked jobs. Manual dispatch remains available after the execution
environment is corrected. No current app, pairing or credential was replaced.

## OpenAI account integration (Linux/gateway source)

- Linux Conexões → OpenAI supports masked API-key entry and official OAuth method
  discovery/start/status/completion, each requiring explicit UI confirmation.
- Keys are registered with `activate: false`. The existing active credential is
  preserved. OpenCode can activate the first credential when none exists; the UI
  states this. Passive-key selection remains in OpenCode, not silently in KzL.
- OAuth completion can select the newly authorized account, with an explicit
  warning; existing records are not deleted. Only recognized official OpenAI
  authorization hosts may be opened, and only after a user gesture.
- Raw credential listings, tokens and provider errors are never proxied to apps.
  Key/code values are absent from gateway operation receipts and local journals.
- One uncertain write fences another. Receipt IDs survive restart; reconciliation
  uses GET-only integration metadata or OAuth status, never automatic resubmission.
  An uncertain start without an attempt ID needs operator review in OpenCode.
- `GET /phone/openai`, `GET /phone/openai/operation`, and POST
  `/phone/openai/{key,oauth,complete}` use the existing paired-device authentication;
  receipts are bound to that device. Browser-origin requests remain forbidden.

Validation: 140 gateway tests and 92 desktop unit tests passed in offline Linux
sandboxes. A native GTK smoke passed in private Xvfb/D-Bus with synthetic keys,
cancelled confirmations, masked entries and lost-acknowledgement recovery. No
browser was opened. The OpenCode 2.2.7 runtime fixture also confirmed actual
inactive dummy credential creation while its previous active credential stayed
active. OAuth exchange tests use a synthetic core, not a real provider account.

Desktop tests now carry their original synthetic transport fixture in
`desktop/transport_fixture.py`; they no longer require unpublished web-preview
files. No real account login or paid model request was initiated.

## Linux deployment 0.8.0

Runtime source: `11dfc92871c5`, installed as a separate read-only release under
`~/.local/share/kzl-center/releases/11dfc92871c5`. All 32 release files and 12
desktop installation files were checked by SHA-256. Only software was backed up;
existing credentials, SSH keys, conversations and preferences were not copied or
replaced. Existing desktop windows were not closed.

Gateway service `opencode-iphone-bridge.service` is active/running with a drop-in
pointing to this release; original unit/source remain untouched. Existing
loopback bind, private Tailscale publishing and paired-device authentication are
preserved. Read-only live health checks returned HTTP 200 for `/api/info`,
`/phone/connections`, `/phone/openai` and registry inventory. The existing 19 MCPs
were available; two existing OpenAI connections remained registered. No managed
MCP declaration or new real credential was created for deployment validation.

OpenCode reported both `pocket.kzl-connections` and `local.linux-computer-use`
active. The adapter was added through a new auto-loaded plugin directory; existing
computer-control plugins, agent settings, consent/pause state and browser pairing
were not altered.

The installed release was exercised in an offline sandbox with the actual
OpenCode binary, authenticated gateway and desktop transport: one-time pairing,
MCP registration, exact-project grant, explicit reject/allow-once, one tool call,
and revocation with no further calls. Its native account UI also passed the
private Xvfb smoke using `/installed`, not the source tree. These are isolated
acceptance checks, not proof of the full workflow on the real iPhone.
