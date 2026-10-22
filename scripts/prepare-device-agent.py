"""Adapt only XCTest metadata for iLoader's extension-prefix validation.

The downloaded original is never overwritten. Output remains unsigned; device
installation and execution must be verified separately.
"""
import hashlib
from pathlib import Path
import plistlib
import sys
import zipfile

source = Path(sys.argv[1])
destination = Path(sys.argv[2])
expected = '40e72380fcb89b2fd71edf7d2766e75c3676e4938af2393db92aecd2b101c46d'
assert hashlib.sha256(source.read_bytes()).hexdigest() == expected, 'Unrecognized source artifact'
assert not destination.exists(), 'Destination already exists; refusing overwrite'
root = 'Payload/devicekit-iosUITests-Runner.app/'
main_id = 'com.mobilenext.devicekit-iosUITests.xctrunner'
plugin_path = root + 'PlugIns/devicekit-iosUITests.xctest/Info.plist'
destination.parent.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(source) as original, zipfile.ZipFile(destination, 'x', compression=zipfile.ZIP_DEFLATED) as output:
    main = plistlib.loads(original.read(root + 'Info.plist'))
    assert main['CFBundleIdentifier'] == main_id
    for entry in original.infolist():
        # Debug symbols are not executable plugins and should not be installed.
        if '.dSYM/' in entry.filename or entry.filename.endswith('.dSYM/'):
            continue
        body = original.read(entry.filename)
        if entry.filename == plugin_path:
            metadata = plistlib.loads(body)
            assert metadata['CFBundlePackageType'] == 'BNDL'
            assert metadata['CFBundleIdentifier'] == 'com.mobilenext.devicekit-iosUITests'
            metadata['CFBundleIdentifier'] = main_id + '.tests'
            body = plistlib.dumps(metadata, fmt=plistlib.FMT_BINARY)
        output.writestr(entry, body)
with zipfile.ZipFile(destination) as archive:
    assert archive.testzip() is None
    plugin = plistlib.loads(archive.read(plugin_path))
    assert plugin['CFBundleIdentifier'].startswith(main_id + '.')
    executable = archive.read(root + 'PlugIns/devicekit-iosUITests.xctest/devicekit-iosUITests')
    with zipfile.ZipFile(source) as original:
        assert executable == original.read(root + 'PlugIns/devicekit-iosUITests.xctest/devicekit-iosUITests')
print('Adapted XCTest metadata; executable bytes unchanged. Re-signing required.')
print(destination)
