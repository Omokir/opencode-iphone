# Testing without repeatedly updating the physical phone

Use `iPhone UI preview` in GitHub Actions for a separate simulator build and
screenshots of fixture screens. It is triggered from the Linux notebook, runs on
macOS, and does not sign/install an IPA, touch the physical phone, use real
credentials, start an API call, or change device-control consent.

The simulator now links the correct WebRTC slice from the same checksum-pinned
XCFramework as the physical build. Preview artifacts upload even when a later
capture fails. Screenshots prove rendering only, not gesture/keyboard behavior.
Older interaction scripts remain separate because they target previous layouts;
they must be adapted and validated before being treated as regression coverage.

Recommended release gate:
1. Unit/transport tests with fixtures (including reordered replies and queue state).
2. Native simulator build and screenshot review from Linux.
3. Focused UI interactions: open history without send, keyboard, tail following,
   navigation and call screen transitions. No real model calls.
4. One consolidated physical release, not an IPA per small change.
5. Physical acceptance for actual microphone/Bluetooth, lock-screen audio,
   CallKit, background lifecycle and signing.

USB-free real-device automation is not enabled. Local Wi-Fi pairing may help in
the future but does not establish internet/4G automation. Free Apple signatures
still expire. A cloud simulator avoids using the user's phone for routine work;
it does not eliminate final physical testing or grant Apple push entitlements.
