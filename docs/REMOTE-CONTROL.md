# Remote control investigation and staged implementation

## Goal

User-owned physical iPhone controlled from notebook across different networks,
using existing Tailscale, without USB. This is not yet a supported capability.
File transfer from Pocket-authorized folders is separate from screen automation.

## Evidence and constraints

Local testing found that USB automation needs a mounted compatible developer
image and an active XCTest runner. Two host daemons previously competed for a
developer-tunnel port; local helper metadata lookup was changed to use lockdown
installation_proxy without starting that tunnel. With image mounted, a real
device UI hierarchy was retrieved over USB. After USB removal, device discovery
was unavailable and the agent port refused TCP over Tailscale even while the
peer was online. This establishes failure of current path, not impossibility of
all wireless approaches. No remote UI control has been demonstrated.

Upstream references:
- https://github.com/mobile-next/mobile-mcp — physical iOS setup documents USB;
  cloud rental devices do not make a personal handset remotely accessible.
- https://github.com/doronz88/pymobiledevice3 — remote pairing/Wi-Fi developer
  tunnels, not proof of unattended cellular operation.
- https://github.com/jkcoxson/idevice — transport, XCTest and WDA components.
- https://github.com/StikDebug/StikDebug — on-device developer-service access
  using pairing plus loopback VPN; not proof of screen control and may conflict
  with existing VPN arrangement. No code incorporated from this project.

## Phase 1 — on-device status probe (0.5.1)

Control panel has an explicit read-only button testing exactly
`http://localhost:8100/status` from the phone, not from notebook. Ephemeral
session has no shared credentials/cookies/cache, rejects redirects, limits
response to 16 KiB and resource timeout to five seconds. Only boolean agent
readiness is decoded; response bodies and errors containing details are not
logged or sent to notebook. HTTP exception is limited to localhost; remote
Pocket API continues using authenticated HTTPS. Test is cancelled on leaving
panel/backgrounding. A positive status is a candidate prerequisite, not
authentication of the listener or proof of remote control. No actions enabled.

Physical validation needed: run after runner initialization, then after USB
removal. The app must state failure rather than imply remote readiness.

## Phase 2 — outbound relay, only after feasibility

If on-device communication and runner lifetime are demonstrated, implement a
phone-initiated authenticated connection over private HTTPS. Do not expose WDA
or lockdown ports. Bind session to paired phone/server and expiring consent.
Use a fixed operation allowlist, bounded payloads, unique request IDs, deadlines,
and read-only status before any UI action. Never expose generic HTTP forwarding,
arbitrary localhost paths, JavaScript evaluation or shell commands. UI actions
retain per-action approvals. Do not replay uncertain actions after reconnect.

Stop/expiry/background/server change must cancel admission and discard queued
actions. Do not promise undo of admitted actions. Screen information must not be
retained in generic logs. Do not forward reusable notebook tokens to runner.

## Phase 3 — physical acceptance

Verify different Wi-Fi and cellular, USB absent, active Tailscale, reboot and
signature expiry behavior, runner termination, foreground app switching, phone
lock, lost network, Stop and consent expiration. No background persistence hacks
or fake audio/location modes. If Pocket suspension prevents forwarding while
another app is open, report that blocker rather than shipping working controls
that silently disconnect. Initial USB bootstrap may remain a requirement.

Do not mark remote control complete until those tests supply actual evidence.
