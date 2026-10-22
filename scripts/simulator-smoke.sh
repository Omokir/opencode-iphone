#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
APP=build/simulator/OpenCodePocket.app
mkdir -p "$APP"
SDK=$(xcrun --sdk iphonesimulator --show-sdk-path)
ARCH=$(uname -m)
xcrun --sdk iphonesimulator swiftc -swift-version 5 -parse-as-library -D SNAPSHOT \
  -target "$ARCH-apple-ios17.0-simulator" -sdk "$SDK" \
  -framework SwiftUI -framework UIKit -framework Security \
  ios/*.swift \
  -o "$APP/OpenCodePocket"
cp ios/Info.plist "$APP/Info.plist"
python3 scripts/icon.py "$APP"
DEVICE=$(xcrun simctl list devices available -j | python3 -c 'import json,sys; d=json.load(sys.stdin); print(next(v["udid"] for k,values in d["devices"].items() if "iOS" in k for v in values if "iPhone" in v["name"]))')
xcrun simctl boot "$DEVICE"
xcrun simctl bootstatus "$DEVICE" -b
xcrun simctl install "$DEVICE" "$APP"
for SCREEN in onboarding chat options models control; do
  xcrun simctl launch "$DEVICE" com.omokir.opencodepocket "--snapshot-$SCREEN"
  sleep 3
  xcrun simctl io "$DEVICE" screenshot "build/iphone-$SCREEN.png"
  xcrun simctl terminate "$DEVICE" com.omokir.opencodepocket
done
