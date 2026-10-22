import plistlib
import struct
import sys
import zipfile

with zipfile.ZipFile(sys.argv[1]) as archive:
    assert archive.testzip() is None, 'Corrupt ZIP'
    root = 'Payload/OpenCodePocket.app/'
    info = plistlib.loads(archive.read(root + 'Info.plist'))
    assert info['CFBundleIdentifier'] == 'com.omokir.opencodepocket'
    assert info['MinimumOSVersion'] == '17.0'
    executable = archive.read(root + info['CFBundleExecutable'])
    assert executable[:4] == b'\xcf\xfa\xed\xfe', 'Expected Mach-O 64-bit'
    assert struct.unpack('<I', executable[4:8])[0] == 0x100000c, 'Expected arm64'
    assert root + 'AppIcon60x60@3x.png' in archive.namelist()
    print('Validated: native arm64 IPA, iOS 17+, bundle com.omokir.opencodepocket, version ' + info['CFBundleShortVersionString'])
    print('Signing and device installation not verified by this validator.')
