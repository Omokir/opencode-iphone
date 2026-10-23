# 0.8.0 — Realtime voice, OpenCode as asynchronous tool

## Setup

Settings → **Voz · OpenAI Realtime**. Paste your OpenAI API project key into
SecureField and save to a separate Keychain item, accessible only while this
device is unlocked, device-only. Never paste Apple credentials or ChatGPT login.
Models: gpt-realtime (default), gpt-realtime-mini, gpt-realtime-2.1. Availability
depends on your API account. Voice: Marin or Cedar. No silent model fallback.

Open a chat and tap phone icon. Explicitly approve paid call and microphone
permission. Audio goes directly to OpenAI, NOT through OpenCode. Realtime can
converse immediately and invoke two narrowly scoped functions to the selected
chat on the paired notebook. OpenCode keeps its existing provider/login/model
and server-side permission policy. No public MCP endpoint or VPN changes needed.

OpenAI Realtime API is billed separately from ChatGPT subscriptions and OpenCode's
provider. Set project spending limits in OpenAI dashboard. Local 15-minute call
cap is NOT a monetary limit; multiple calls can incur further cost. No API calls
are made by simply saving key, opening settings or running native policy tests.

## Transport and interruption

This first native implementation uses documented Realtime GA WebSocket events,
not a WebView or chained transcription-to-OpenCode-to-TTS. Microphone is resampled
to mono PCM16 little-endian, 24 kHz. AVAudioEngine voice processing/voiceChat mode
provides echo processing; headset is recommended for physical validation.
OpenAI recommends WebRTC for robust mobile transport; native WebSocket lets this
standalone Swift build avoid adding/signing a third-party WebRTC framework.
Latency and barge-in quality must be tested on actual device/network.

Permanent key is used only for a bounded, non-redirecting request to
`https://api.openai.com/v1/realtime/client_secrets`. A short-lived 60-second token
authenticates fixed `wss://api.openai.com/v1/realtime` endpoint. Key/token never
goes to notebook, chat cache, diagnostics or logs. There is no custom endpoint
field or insecure-certificate override. Secret responses/events are not logged.
Provider's own retention/processing policies still apply; disabled session tracing
does not imply zero provider retention. Swift Strings are not guaranteed zeroized.

Server VAD handles continuous turns and cancels response when speech begins.
Client immediately clears scheduled playback and truncates unheard audio items
using a conservative lower bound of fully-played buffers. Late audio from an
interrupted response is ignored. This is not a sample-perfect playback guarantee.
Input buffering is bounded to eight chunks; congestion ends call rather than
accumulating microphone audio. Output queue caps at 20 seconds, incoming events
at 512 KiB and individual PCM chunks at 256 KiB. Non-finite/out-of-range samples
are clipped safely. No local audio recording or persisted voice transcript.

**Mudo** stops microphone delivery and clears unsent server input. **Parar somente
fala** cancels response/playback, not notebook work. **Encerrar** closes socket,
stops audio engine, cancels local monitoring, discards pending proposals and clears
caption. It does not undo/cancel an already-admitted OpenCode prompt. App background,
audio interruption, device/server disconnect/change and leaving voice panel end
the call. No automatic reconnect, background microphone or paid retry.

## Tool execution and safety

- `opencode_submit({task})`: proposal only; full text shown in native UI, requires
  explicit button confirmation (and app's optional device authentication). One
  task/proposal at a time, bounded task size. New speech before confirmation
  rejects stale proposal. No automatic send based on voice alone.
- `opencode_status({})`: reads only selected chat's state and bounded recent
  assistant text. Call consent discloses that these results can go to OpenAI.
  No attachment bytes, raw permission input or generic configuration endpoint.

Only completed `response.done` outputs dispatch functions. Intermediate argument
events, incomplete/cancelled responses, unknown names, arbitrary paths/session IDs
and extra arguments cannot submit work. Call IDs are deduplicated, max 32 per call.
Tool data is marked untrusted; model instructions are NOT sole authorization
boundary. Each submit uses one generated message ID, no uncertain-write replay.

After native approval, function output remains pending asynchronously while
OpenCode works; voice session can continue conversing. Monitor checks actual
user message ID and completed assistant response before returning result. It
preserves existing permission/question UI; approvals stay manual and allow-once
or reject. Result is bounded recent selected-chat text, not proof that every
action succeeded. Other desktop clients modifying same chat can complicate
association; avoid concurrent writes during a voice task.

Monitoring is bounded to 300 foreground poll iterations; timeout/lost connection
returns pending/uncertain, never fabricated success. Notebook work can continue.
Use separate **Interromper tarefa no notebook** button for explicit cancellation;
this is not rollback. Permission/form contents are reviewed locally rather than
spoken or automatically approved. Form panel mutes microphone; unmute manually.

## Verification limits

Pure native tests validate complete vs cancelled tool dispatch, strict argument
scope, PCM endian, size bounds and sample clipping. Device build/link verifies
AVFAudio/AVFoundation and microphone usage declaration. No paid OpenAI session,
microphone capture, acoustic barge-in or live execution is performed in CI or
without user tapping Ligar. Physical acceptance requires user's own key and
separate confirmation; compilation is not proof of end-to-end audio behavior.

References reviewed:
- https://developers.openai.com/api/docs/guides/realtime-websocket
- https://developers.openai.com/api/docs/guides/realtime-conversations
- https://developers.openai.com/api/reference/resources/realtime/subresources/client_secrets/methods/create
- https://developer.apple.com/documentation/avfaudio
