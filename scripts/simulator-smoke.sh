#!/bin/bash
set -euo pipefail
timed() {
  python3 - "$@" <<'PY'
import subprocess, sys, time
seconds = int(sys.argv[1]); command = sys.argv[2:]
started = time.monotonic()
print('UI command:', ' '.join(command), flush=True)
subprocess.run(command, check=True, timeout=seconds)
print('UI command finished in', round(time.monotonic() - started, 1), 'seconds', flush=True)
PY
}
cd "$(dirname "$0")/.."
APP=build/simulator/OpenCodePocket.app
mkdir -p "$APP"
SDK=$(xcrun --sdk iphonesimulator --show-sdk-path)
ARCH=$(uname -m)
if [ ! -d build/WebRTC.xcframework ]; then
  curl --fail --location --retry 2 'https://github.com/stasel/WebRTC/releases/download/156.0.0/WebRTC-M156.xcframework.zip' -o build/WebRTC.zip
  echo '43c2a6f7a650185bbc911d7605a979589671886e8fc0ac283f54fdf3f511dc46  build/WebRTC.zip' | shasum -a 256 -c -
  unzip -q build/WebRTC.zip -d build
fi
RTC=$(python3 -c 'import plistlib; p="build/WebRTC.xcframework"; v=plistlib.load(open(p+"/Info.plist","rb")); print(p+"/"+next(x["LibraryIdentifier"] for x in v["AvailableLibraries"] if x.get("SupportedPlatformVariant")=="simulator" and "'"$ARCH"'" in x["SupportedArchitectures"]))')
mkdir -p "$APP/Frameworks"
cp -R "$RTC/WebRTC.framework" "$APP/Frameworks/"
xcrun --sdk iphonesimulator swiftc -swift-version 5 -parse-as-library -D SNAPSHOT \
  -F "$RTC" -framework WebRTC -framework CallKit -Xlinker -rpath -Xlinker @executable_path/Frameworks \
  -target "$ARCH-apple-ios17.0-simulator" -sdk "$SDK" \
  -framework SwiftUI -framework UIKit -framework Security -framework CryptoKit -framework QuickLook -framework ImageIO -framework LocalAuthentication -framework UserNotifications -framework AVFoundation -framework AVFAudio -framework AVKit \
  ios/*.swift \
  -o "$APP/OpenCodePocket"
cp ios/Info.plist "$APP/Info.plist"
cp ios/PrivacyInfo.xcprivacy "$APP/PrivacyInfo.xcprivacy"
cp ios/Resources/KzL.png "$APP/KzL.png"
python3 scripts/icon.py "$APP"
DEVICE=$(python3 - <<'PY'
import json, subprocess
def read(*args): return json.loads(subprocess.check_output(['xcrun', 'simctl', 'list', *args, '-j']))
types = read('devicetypes')['devicetypes']
phone = next((t['identifier'] for t in types if t['name'] == 'iPhone 11'), None)
runtimes = [r for r in read('runtimes')['runtimes'] if r.get('isAvailable') and r['name'].startswith('iOS')]
if phone and runtimes:
    for runtime in sorted(runtimes, key=lambda r: tuple(map(int, r['version'].split('.'))), reverse=True):
        result = subprocess.run(['xcrun', 'simctl', 'create', 'Pocket iPhone 11', phone, runtime['identifier']], text=True, capture_output=True)
        if result.returncode == 0:
            print(result.stdout.strip())
            raise SystemExit(0)
devices = read('devices', 'available')['devices']
print(next(d['udid'] for key, group in devices.items() if 'iOS' in key for d in group if 'iPhone' in d['name']))
PY
)
timed 60 xcrun simctl boot "$DEVICE"
defaults write com.apple.iphonesimulator ConnectHardwareKeyboard -bool false
open -a "$(xcode-select -p)/Applications/Simulator.app" --args -CurrentDeviceUDID "$DEVICE"
timed 300 xcrun simctl bootstatus "$DEVICE" -b
timed 180 xcrun simctl install "$DEVICE" "$APP"
xcrun simctl status_bar "$DEVICE" override --time '9:41' --batteryState charged --batteryLevel 100
for SCREEN in ${UI_SCREEN_LIST:-onboarding conversation sidebar call live chat options models control sessions question files inbox}; do
  timed 360 xcrun simctl launch "$DEVICE" com.omokir.opencodepocket "--snapshot-$SCREEN"
  sleep 3
  xcrun simctl io "$DEVICE" screenshot "build/iphone-$SCREEN.png"
  xcrun simctl terminate "$DEVICE" com.omokir.opencodepocket
done

if [ "${SNAPSHOTS_ONLY:-0}" = "1" ] && [ "${UI_INTERACTIONS:-0}" != "1" ]; then exit 0; fi

# Interaction test, not a fixture screenshot: open the actual system picker.
npm install --prefix build/ui-tools --no-audit --no-fund mobilecli@1.0.21
CLI="$PWD/build/ui-tools/node_modules/.bin/mobilecli"
export MOBILECLI_HOME="$PWD/build/mobilecli-simulator"
"$CLI" agent install --device "$DEVICE"
"$CLI" device info --device "$DEVICE" > build/simulator-device-info.json
python3 scripts/design-smoke.py "$CLI" "$DEVICE"
