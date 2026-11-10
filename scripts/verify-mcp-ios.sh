#!/bin/bash
# Parent-side orchestration: all Swift compilation/test execution is sandboxed.
set -euo pipefail
SOURCE="$(pwd -P)"
RTC="$(cd "$1" && pwd -P)"
BASE="$(mktemp -d "${RUNNER_TEMP:-/tmp}/kzl-native.XXXXXX")"
SCRATCH="$BASE/volume"
mkdir -p "$SCRATCH"
# A private fixed-size volume bounds total writable test/compiler storage.
hdiutil create -quiet -size 1g -fs HFS+ -volname KzLNative "$BASE/scratch.dmg"
hdiutil attach -quiet -nobrowse -mountpoint "$SCRATCH" "$BASE/scratch.dmg"
trap 'hdiutil detach -quiet "$SCRATCH" || true' EXIT
mkdir -p "$SCRATCH/home" "$SCRATCH/tmp" "$SCRATCH/cache"
SWIFTC="$(xcrun --find swiftc)"
SDK="$(xcrun --sdk iphoneos --show-sdk-path)"
MACSDK="$(xcrun --sdk macosx --show-sdk-path)"
PROFILE="$BASE/offline.sb"
cat > "$PROFILE" <<EOF
(version 1)
(deny default)
(allow process-exec)
(allow process-fork)
(allow signal (target self))
(allow sysctl-read)
(allow file-read*
  (subpath "/Applications") (subpath "/System") (subpath "/Library")
  (subpath "/usr") (subpath "/bin") (subpath "/sbin")
  (subpath "/private/etc") (subpath "/private/var/db")
  (subpath "/dev")
  (subpath "$SOURCE") (subpath "$RTC") (subpath "$SCRATCH"))
(allow file-write* (subpath "$SCRATCH") (literal "/dev/null"))
EOF
# No network, inherited environment, credential sockets, user HOME or writable
# source are exposed. Resource limits apply to compiler and test descendants.
ulimit -t 240
# Darwin rejects RLIMIT_AS and RLIMIT_DATA on this runner. Set only the
# supported soft resident-set policy, preserving the runner's hard ceiling.
ulimit -S -m 1048576
ulimit -u 64
ulimit -f 262144
run() {
  /usr/bin/env -i HOME="$SCRATCH/home" TMPDIR="$SCRATCH/tmp" PATH=/usr/bin:/bin \
    /usr/bin/sandbox-exec -f "$PROFILE" "$@"
}
run "$SWIFTC" -target "$(uname -m)-apple-macos13.0" -sdk "$MACSDK" \
  -module-cache-path "$SCRATCH/cache" -parse-as-library -framework CryptoKit \
  ios/MCPRegistry.swift tests/MCPRegistryTests.swift -o "$SCRATCH/mcp-registry-test"
run "$SCRATCH/mcp-registry-test"
run "$SWIFTC" -target "$(uname -m)-apple-macos13.0" -sdk "$MACSDK" \
  -module-cache-path "$SCRATCH/cache" -parse-as-library \
  ios/RealtimeProtocol.swift ios/VoiceDiagnostics.swift tests/VoiceProtocolTests.swift -o "$SCRATCH/voice-test"
run "$SCRATCH/voice-test"
run "$SWIFTC" -typecheck -swift-version 5 -target arm64-apple-ios17.0 -sdk "$SDK" \
  -module-cache-path "$SCRATCH/cache" -F "$RTC" -framework WebRTC ios/*.swift
echo 'PASS: offline registry/voice native tests and all iPhone SwiftUI sources typechecked'
