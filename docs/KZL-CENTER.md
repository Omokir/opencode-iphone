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

- Adapter installation in the real user environment and native UI validation.
- Provider sign-in/API-key entry and secure Linux vault integration.
- Installed updated gateway/desktop, iOS build/sign/install, screenshots and
  end-to-end tests on the owner's actual iPhone.
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
