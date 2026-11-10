"""Trusted parent watchdog; target subprocess receives no inherited credentials.

Memory/vCPU are bounded by the verified disposable runner VM; Seatbelt restricts
target filesystem/network, private volume bounds disk, rlimits bound processes,
CPU and files, and this parent bounds each command's wall-clock lifetime.
"""
import os
import signal
import subprocess
import sys
import resource

assert os.getuid() == 65000, 'Dedicated unprivileged fixture user required'
resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
resource.setrlimit(resource.RLIMIT_CPU, (240, 240))
resource.setrlimit(resource.RLIMIT_FSIZE, (128 * 1024 * 1024, 128 * 1024 * 1024))
environment = {key: os.environ[key] for key in ('HOME', 'TMPDIR', 'PATH')}
process = subprocess.Popen(['/usr/bin/sandbox-exec', '-f', sys.argv[1], *sys.argv[2:]],
                           env=environment, start_new_session=True)
try:
    code = process.wait(timeout=180)
except subprocess.TimeoutExpired:
    os.killpg(process.pid, signal.SIGKILL)
    process.kill(); process.wait(timeout=10)
    print('BLOCKED: sandbox command exceeded 180-second lifetime.', file=sys.stderr)
    code = 124
finally:
    # Reap/terminate any remaining children in this invocation's private group.
    try: os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError: pass
raise SystemExit(code)
