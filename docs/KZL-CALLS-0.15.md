# KzL calls and recorded computer activity — 0.15.0

This version introduces an outgoing CallKit owner independent of the chat sheet.
Minimizing the call leaves the owner alive, with a return button in the unlocked
app. The normal privacy lock still hides chats on background entry; it does not
grant access to conversations through the call UI. Calls use the background audio
mode with actual WebRTC audio, not silent keepalive playback. The app registers no
incoming PushKit/APNs calls and never automatically starts a new paid session.

WebRTC uses manual audio activation for system calls. CallKit activates/deactivates
the audio session; end, reset, initialization failure and the existing call time
limit stop voice. Switching computers ends the active call. Other chat Live stays
foreground-only. Concurrent KzL and Live audio sessions are rejected.

**Not validated yet:** physical lock-screen audio, CallKit audio activation on the
signed IPA, Bluetooth/cellular interruption, minimized return and long-running
delegation. A successful build is not evidence these scenarios work. Test on the
owner's iPhone only after explicit call initiation. The API remains separately
billed. No call or microphone capture was started by CI.

Computer activity is read-only and task-scoped. It projects stored tool names,
states and timestamps. A user may request an embedded PNG/JPEG/WebP screenshot
from a specific child-session message, tool ID and content index. The server never
fetches a submitted URL or reads a submitted path. It accepts only recorded inline
raster content, bounds bytes, and disables caching. Client downsamples previews.
External/content-addressed tool attachments are not yet supported by this path;
an absent preview is not proof that no screenshot was taken. There is no video
stream, click injection or new desktop permission in this UI.

KzL avatar loads a bundled `KzL.png` if present. The original uploaded avatar has
not yet been available as a readable local file; the fallback is a text mark,
not an imitation claimed to be the original. The private user's active KzL model
was selected as `openai/gpt-6.1-terra-fast`; portable code does not hardcode their
session ID, credentials or force this model on other installations.

Remaining: full tool discovery through a supported OpenCode catalog adapter,
server-independent KzL memory, confirmed resolution of the reported keyboard and
history bug on the physical device, and the original avatar asset.
