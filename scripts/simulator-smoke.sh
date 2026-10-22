#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
APP=build/simulator/OpenCodePocket.app
mkdir -p "$APP"
SDK=$(xcrun --sdk iphonesimulator --show-sdk-path)
ARCH=$(uname -m)
xcrun --sdk iphonesimulator swiftc -swift-version 5 -parse-as-library \
  -target "$ARCH-apple-ios17.0-simulator" -sdk "$SDK" \
  -framework SwiftUI -framework UIKit -framework Security \
  ios/Models.swift ios/API.swift ios/ChatStore.swift ios/OpenCodePhone.swift \
  -o "$APP/OpenCodePocket"
cp ios/Info.plist "$APP/Info.plist"
python3 scripts/icon.py "$APP"
DEVICE=$(xcrun simctl list devices available -j | python3 -c 'import json,sys; d=json.load(sys.stdin); print(next(v["udid"] for k,values in d["devices"].items() if "iOS" in k for v in values if "iPhone" in v["name"]))')
xcrun simctl boot "$DEVICE"
xcrun simctl bootstatus "$DEVICE" -b
xcrun simctl install "$DEVICE" "$APP"
xcrun simctl launch "$DEVICE" com.omokir.opencodepocket
sleep 4
xcrun simctl io "$DEVICE" screenshot build/iphone-onboarding.png
xcrun simctl terminate "$DEVICE" com.omokir.opencodepocket
