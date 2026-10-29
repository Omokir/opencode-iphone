#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
APP=build/Payload/OpenCodePocket.app
mkdir -p "$APP"
SDK=$(xcrun --sdk iphoneos --show-sdk-path)
RTC=build/WebRTC.xcframework/ios-arm64
if [ ! -d "$RTC/WebRTC.framework" ]; then
  curl --fail --location --retry 2 'https://github.com/stasel/WebRTC/releases/download/156.0.0/WebRTC-M156.xcframework.zip' -o build/WebRTC.zip
  echo '43c2a6f7a650185bbc911d7605a979589671886e8fc0ac283f54fdf3f511dc46  build/WebRTC.zip' | shasum -a 256 -c -
  unzip -q build/WebRTC.zip -d build
fi
mkdir -p "$APP/Frameworks"
cp -R "$RTC/WebRTC.framework" "$APP/Frameworks/"
xcrun --sdk iphoneos swiftc -swift-version 5 -parse-as-library -O \
  -target arm64-apple-ios17.0 -sdk "$SDK" \
  -F "$RTC" -framework WebRTC \
  -framework SwiftUI -framework UIKit -framework Security -framework CryptoKit -framework QuickLook -framework ImageIO -framework LocalAuthentication -framework UserNotifications -framework AVFoundation -framework AVFAudio -framework AVKit \
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
