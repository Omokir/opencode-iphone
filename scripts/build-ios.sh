#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
APP=build/Payload/OpenCodePocket.app
mkdir -p "$APP"
SDK=$(xcrun --sdk iphoneos --show-sdk-path)
xcrun --sdk iphoneos swiftc -swift-version 5 -parse-as-library -O \
  -target arm64-apple-ios17.0 -sdk "$SDK" \
  -framework SwiftUI -framework UIKit -framework Security -framework CryptoKit -framework QuickLook -framework ImageIO -framework LocalAuthentication \
  -Xlinker -rpath -Xlinker @executable_path/Frameworks \
  ios/*.swift \
  -o "$APP/OpenCodePocket"
cp ios/Info.plist "$APP/Info.plist"
cp ios/PrivacyInfo.xcprivacy "$APP/PrivacyInfo.xcprivacy"
python3 scripts/icon.py "$APP"
/usr/libexec/PlistBuddy -c 'Add :CFBundleSupportedPlatforms array' "$APP/Info.plist"
/usr/libexec/PlistBuddy -c 'Add :CFBundleSupportedPlatforms:0 string iPhoneOS' "$APP/Info.plist"
printf 'APPL????' > "$APP/PkgInfo"
cd build
zip -qr OpenCode-Pocket-unsigned.ipa Payload
cd ..
python3 scripts/validate-ipa.py build/OpenCode-Pocket-unsigned.ipa
