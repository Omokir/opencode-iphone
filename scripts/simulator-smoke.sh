#!/bin/bash
set -euo pipefail
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
python3 scripts/icon.py "$APP"
DEVICE=$(xcrun simctl list devices available -j | python3 -c 'import json,sys; d=json.load(sys.stdin); print(next(v["udid"] for k,values in d["devices"].items() if "iOS" in k for v in values if "iPhone" in v["name"]))')
xcrun simctl boot "$DEVICE"
xcrun simctl bootstatus "$DEVICE" -b
xcrun simctl install "$DEVICE" "$APP"
for SCREEN in onboarding chat options models control sessions question files inbox; do
  xcrun simctl launch "$DEVICE" com.omokir.opencodepocket "--snapshot-$SCREEN"
  sleep 3
  xcrun simctl io "$DEVICE" screenshot "build/iphone-$SCREEN.png"
  xcrun simctl terminate "$DEVICE" com.omokir.opencodepocket
done

if [ "${SNAPSHOTS_ONLY:-0}" = "1" ]; then exit 0; fi

# Interaction test, not a fixture screenshot: open the actual system picker.
npm install --prefix build/ui-tools --no-audit --no-fund mobilecli@1.0.21
CLI="$PWD/build/ui-tools/node_modules/.bin/mobilecli"
export MOBILECLI_HOME="$PWD/build/mobilecli-simulator"
"$CLI" agent install --device "$DEVICE"
"$CLI" device info --device "$DEVICE" > build/simulator-device-info.json
xcrun simctl addmedia "$DEVICE" "$APP/Artwork.png"
xcrun simctl launch "$DEVICE" com.omokir.opencodepocket --snapshot-chat
python3 scripts/photo-picker-smoke.py "$CLI" "$DEVICE"
xcrun simctl terminate "$DEVICE" com.omokir.opencodepocket
xcrun simctl launch "$DEVICE" com.omokir.opencodepocket --snapshot-sessions
python3 scripts/pins-smoke.py "$CLI" "$DEVICE"
xcrun simctl terminate "$DEVICE" com.omokir.opencodepocket
python3 scripts/chat-files-smoke.py "$CLI" "$DEVICE"
