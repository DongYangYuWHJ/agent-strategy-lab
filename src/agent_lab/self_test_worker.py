"""Run advisory unittest files in a disposable copy, without provider credentials.

Python audit hooks constrain accidental filesystem/network/process access; this is
not an OS sandbox for hostile native code. Hidden acceptance is never run here.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import sysconfig
import unittest


def main():
    root = Path(sys.argv[1]).resolve()
    scratch = root / 'scratch'
    scratch.mkdir()
    readable = [root, Path(sysconfig.get_path('stdlib')).resolve(), Path(sys.base_prefix).resolve()]

    def inside(path, roots):
        if isinstance(path, int):
            return False
        try:
            resolved = Path(os.fsdecode(path)).resolve()
            return any(resolved.is_relative_to(r) for r in roots)
        except (TypeError, ValueError, OSError):
            return False

    def audit(event, args):
        if (event.startswith(('socket.', 'subprocess.', 'ctypes.', 'winreg.'))
                or event in {'os.system', 'os.fork', 'os.startfile', 'os.exec', 'os.spawn', 'os.posix_spawn'}):
            raise PermissionError('Self-tests cannot use network, native calls, or child processes')
        if event == 'open':
            path, mode, flags = args
            writing = (isinstance(mode, str) and any(c in mode for c in 'wax+')) or bool(
                flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            if not inside(path, [scratch] if writing else readable):
                raise PermissionError('Self-test file access outside allowed copy')
        if event in {'os.listdir', 'os.scandir', 'os.chdir'} and not inside(args[0], readable):
            raise PermissionError('Self-test directory access outside allowed copy')
        if event in {'os.remove', 'os.rmdir', 'os.mkdir', 'os.chmod', 'os.utime', 'os.truncate', 'os.link', 'os.symlink', 'os.rename'}:
            paths = args[:2] if event in {'os.link', 'os.symlink', 'os.rename'} else args[:1]
            if any(not inside(p, [scratch]) for p in paths):
                raise PermissionError('Self-tests may only write scratch files')

    class Output(io.StringIO):
        def write(self, value):
            if self.tell() + len(value) > 64000:
                raise RuntimeError('Self-test output exceeded 64000 characters')
            return super().write(value)

    sys.path[:0] = [str(root / 'src'), str(root)]
    os.chdir(root)
    sys.addaudithook(audit)
    output = Output()
    record = {'advisory_only': True, 'passed': False, 'tests_run': 0}
    try:
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            suite = unittest.defaultTestLoader.discover(str(root / 'agent_tests'), pattern='test_*.py')
            result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
            record.update(tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                          skipped=len(result.skipped), expected_failures=len(result.expectedFailures),
                          passed=result.wasSuccessful() and result.testsRun > len(result.skipped) + len(result.expectedFailures))
    except BaseException as exc:
        record['error'] = type(exc).__name__ + ': ' + str(exc)[:500]
    record['output'] = output.getvalue()[:64000]
    print(json.dumps(record, ensure_ascii=True), flush=True)


if __name__ == '__main__':
    main()
