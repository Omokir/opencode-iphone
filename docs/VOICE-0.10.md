# Voice 0.10 — physical acceptance pending

Realtime uses native WebRTC (stasel WebRTC M156, pinned archive SHA-256 in
build-ios.sh). Only audio track and bounded JSON data channel are created; no
camera. Device build embeds the arm64 framework for signing with the app.

Phone queries authenticated experimental OpenCode voice inventory, then sends
one SDP offer to the notebook broker. Only gpt-realtime-2.1 WebRTC is enabled
through the phone gateway. Permanent OpenAI key stays in OpenCode credential
storage; old iPhone voice keys are ignored and may be manually removed.
Existing coding account, model, tool approvals and task journal remain intact.
No automatic retries, model fallback, or reconnection after paid admission.

WebRTC owns capture, echo processing, decoding and playout instead of manual
PCM/base64 over WebSocket. Incoming VAD interruption and explicit stop clear
WebRTC output, without inventing local PCM truncation offsets. Ending call
does not cancel admitted notebook work. Calls remain foreground-only.

Session readiness and server output-buffer events are not proof of audible
sound. Local tone uses the legacy local test engine, NOT the WebRTC media path.
No microphone meter or persisted transcripts are claimed. Usage is reported
from provider events; time cap is not a monetary cap.

Owner-attended acceptance: local output, isolated conversation, speaker and
headphones, interruptions, mute, route changes, background, disconnect, then
read-only status and approved task/recovery. Build success cannot substitute
for those checks. No paid session is started by tests or installation.
