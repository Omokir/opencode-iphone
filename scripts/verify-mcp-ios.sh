#!/bin/bash
# Parent-side orchestration: all Swift compilation/test execution is sandboxed.
set -euo pipefail
if [[ "${GITHUB_ACTIONS:-}" != true || "${RUNNER_OS:-}" != macOS || "${RUNNER_ARCH:-}" != ARM64 ]]; then
  echo 'BLOCKED: requires a fresh standard GitHub arm64 macOS VM.' >&2; exit 78
fi
# Darwin does not enforce address-space/RSS rlimits. Memory/CPU isolation is
# instead the standard runner VM's hypervisor boundary (documented 7 GB/3 CPUs).
# Verify actual guest capacity; never silently use a larger/shared host.
RAM="$(/usr/sbin/sysctl -n hw.memsize)"
CPUS="$(/usr/sbin/sysctl -n hw.ncpu)"
if (( RAM > 8589934592 || CPUS > 3 || RAM < 1073741824 )); then
  echo 'BLOCKED: runner exceeds declared 8-GiB/3-vCPU VM resource ceiling.' >&2; exit 78
fi
echo "Verified dedicated VM resource boundary: ${RAM} bytes RAM, ${CPUS} vCPUs"
SOURCE="$(pwd -P)"
RTC="$(cd "$1" && pwd -P)"
BASE="$(mktemp -d "${RUNNER_TEMP:-/tmp}/kzl-native.XXXXXX")"
SCRATCH="/Volumes/KzLNative-$(uuidgen)"
# A private fixed-size volume bounds total writable test/compiler storage.
hdiutil create -quiet -size 1g -fs HFS+ -volname KzLNative "$BASE/scratch.dmg"
hdiutil attach -quiet -nobrowse -owners on -mountpoint "$SCRATCH" "$BASE/scratch.dmg"
trap 'hdiutil detach -quiet "$SCRATCH" || true' EXIT
WORK="$SCRATCH/work"
mkdir -p "$WORK/home" "$WORK/tmp" "$WORK/cache" "$SCRATCH/source/ios" "$SCRATCH/source/tests" "$SCRATCH/rtc" "$SCRATCH/support"
# Copy only compilation inputs, never runner HOME, git auth, sockets or caches.
cp ios/*.swift "$SCRATCH/source/ios/"
cp tests/MCPRegistryTests.swift tests/VoiceProtocolTests.swift "$SCRATCH/source/tests/"
ditto "$RTC/WebRTC.framework" "$SCRATCH/rtc/WebRTC.framework"
cp scripts/macos-sandbox-run.py "$SCRATCH/support/watchdog.py"
SOURCE="$SCRATCH/source"
RTC="$SCRATCH/rtc"
USER_NAME=kzlfixture
if id "$USER_NAME" >/dev/null 2>&1 || [[ -n "$(dscl . -search /Users UniqueID 65000)" ]]; then
  echo 'BLOCKED: fixture user/UID already exists.' >&2; exit 78
fi
sudo dscl . -create "/Users/$USER_NAME"
sudo dscl . -create "/Users/$USER_NAME" UniqueID 65000
sudo dscl . -create "/Users/$USER_NAME" PrimaryGroupID 20
sudo dscl . -create "/Users/$USER_NAME" NFSHomeDirectory "$WORK/home"
sudo dscl . -create "/Users/$USER_NAME" UserShell /usr/bin/false
sudo dscl . -create "/Users/$USER_NAME" Password '*'
sudo chown -R 65000:20 "$WORK"
chmod 755 "$SCRATCH"
SWIFTC="$(xcrun --find swiftc)"
SDK="$(xcrun --sdk iphoneos --show-sdk-path)"
MACSDK="$(xcrun --sdk macosx --show-sdk-path)"
PROFILE="$SCRATCH/support/offline.sb"
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
  (subpath "$SOURCE") (subpath "$RTC") (subpath "$WORK"))
(allow file-write* (subpath "$WORK") (literal "/dev/null"))
EOF
find "$SCRATCH/source" "$SCRATCH/rtc" "$SCRATCH/support" -type f -exec chmod 444 {} +
find "$SCRATCH/source" "$SCRATCH/rtc" "$SCRATCH/support" -type d -exec chmod 555 {} +
# No network, inherited environment, credential sockets, user HOME or writable
# source are exposed. Resource limits apply to compiler and test descendants.
run() {
  sudo -u "$USER_NAME" /usr/bin/env -i HOME="$WORK/home" TMPDIR="$WORK/tmp" PATH=/usr/bin:/bin \
    /usr/bin/python3 -I "$SCRATCH/support/watchdog.py" "$PROFILE" "$@"
}
cd "$SOURCE"
run "$SWIFTC" -target "$(uname -m)-apple-macos13.0" -sdk "$MACSDK" \
  -module-cache-path "$WORK/cache" -parse-as-library -framework CryptoKit \
  ios/MCPRegistry.swift tests/MCPRegistryTests.swift -o "$WORK/mcp-registry-test"
run "$WORK/mcp-registry-test"
run "$SWIFTC" -target "$(uname -m)-apple-macos13.0" -sdk "$MACSDK" \
  -module-cache-path "$WORK/cache" -parse-as-library \
  ios/RealtimeProtocol.swift ios/VoiceDiagnostics.swift tests/VoiceProtocolTests.swift -o "$WORK/voice-test"
run "$WORK/voice-test"
run "$SWIFTC" -typecheck -swift-version 5 -target arm64-apple-ios17.0 -sdk "$SDK" \
  -module-cache-path "$WORK/cache" -F "$RTC" -framework WebRTC ios/*.swift
echo 'PASS: offline registry/voice native tests and all iPhone SwiftUI sources typechecked'
