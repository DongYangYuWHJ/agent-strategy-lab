"""Agent-written advisory tests, separate from operator acceptance and source."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from .domain import save_json, bounded_timeout
from .tools import definition
from .workspace import file_hash

SELF_TEST_TOOLS = [
    definition('list_tests', 'List agent-written advisory tests and latest run; not operator acceptance.', {}),
    definition('read_test', 'Read an agent-written unittest file (test_NAME.py).', {'name': {'type': 'string'}}),
    definition('write_test', 'Create/replace test_NAME.py with unittest.TestCase tests. Import app or project packages. Tests run in a disposable source copy; scratch/ is writable. No network, subprocess, external files or hidden checks.',
               {'name': {'type': 'string'}, 'content': {'type': 'string'}}),
    definition('run_self_tests', 'Run all agent-written unittest tests against a disposable copy of CURRENT code. Returns advisory evidence only; no hidden acceptance. 30-second process timeout.', {}),
]
SELF_TEST_NAMES = {t['name'] for t in SELF_TEST_TOOLS}


class SelfTests:
    def __init__(self, directory, workspace):
        self.root = directory / 'self-tests'
        self.source = self.root / 'source'
        self.source.mkdir(parents=True)
        self.workspace = workspace
        self.counter = 0
        self.latest = None

    def path(self, name):
        if not isinstance(name, str) or not re.fullmatch(r'test_[A-Za-z0-9_]{1,70}\.py', name):
            raise ValueError('Use a flat unittest filename test_NAME.py')
        path = self.source / name
        if path.is_symlink():
            raise ValueError('Test symlinks are not allowed')
        return path

    def fingerprint(self):
        return {p.name: file_hash(p) for p in sorted(self.source.iterdir()) if p.is_file()}

    def snapshot(self, target):
        shutil.copytree(self.source, target)

    def execute(self, call, remaining):
        definition = next(t for t in SELF_TEST_TOOLS if t['name'] == call.name)
        if (set(call.arguments) != set(definition['parameters']['properties'])
                or any(not isinstance(v, str) for v in call.arguments.values())):
            raise ValueError('Self-test tool arguments do not match schema')
        if call.name == 'list_tests':
            latest = ({**self.latest, 'output': self.latest.get('output', '')[:12000]}
                      if self.latest is not None else None)
            return {'ok': True, 'tests': self.fingerprint(), 'latest_run': latest}
        if call.name == 'read_test':
            return {'ok': True, 'name': call.arguments['name'],
                    'content': self.path(call.arguments['name']).read_text(encoding='utf-8')}
        if call.name == 'write_test':
            path = self.path(call.arguments['name'])
            content = call.arguments['content']
            if len(content.encode('utf-8')) > 64000:
                raise ValueError('Test file exceeds 64000 bytes')
            if not path.exists() and len(self.fingerprint()) >= 20:
                raise ValueError('At most 20 self-test files')
            path.write_text(content, encoding='utf-8')
            return {'ok': True, 'name': path.name, 'bytes': path.stat().st_size}
        return self.run(remaining)

    def run(self, remaining):
        self.workspace.verify_immutable()
        self.counter += 1
        timeout = bounded_timeout(30, remaining)
        before = self.fingerprint()
        code_before = {n: file_hash(self.workspace.resolve(n)) for n in self.workspace.list_files()}
        started = time.monotonic()
        self.latest = {'ok': True, 'advisory_only': True, 'passed': False, 'status': 'completed',
                       'tests_run': 0, 'source_hashes': code_before, 'test_hashes': before}
        env = {k: os.environ[k] for k in ('SystemRoot', 'WINDIR', 'LANG') if k in os.environ}
        with tempfile.TemporaryDirectory(dir=self.root) as temp:
            root = Path(temp)
            for name in self.workspace.list_files():
                dest = root / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(self.workspace.resolve(name), dest)
            if (root / 'agent_tests').exists() or (root / 'scratch').exists():
                raise ValueError('Task uses reserved self-test directories')
            shutil.copytree(self.source, root / 'agent_tests')
            env['TEMP'] = env['TMP'] = str(root)
            worker = Path(__file__).with_name('self_test_worker.py')
            self.latest['worker_sha256'] = file_hash(worker)
            try:
                # No shell and no arbitrary command supplied by the model.
                result = subprocess.run([sys.executable, '-I', '-B', '-X', 'utf8', str(worker.resolve()), str(root.resolve())],
                    cwd=root, env=env, stdin=subprocess.DEVNULL, capture_output=True,
                    timeout=timeout, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                if result.returncode or len(result.stdout) > 1048576:
                    raise ValueError('Self-test process did not produce a bounded result')
                response = json.loads(result.stdout)
                self.latest.update(response)
            except subprocess.TimeoutExpired:
                self.latest.update(status='timed_out', passed=False, output='Self-tests exceeded 30-second execution allowance')
            except (ValueError, UnicodeError) as exc:
                self.latest.update(status='incomplete', passed=False, output=str(exc)[:500])
        self.workspace.verify_immutable()
        if before != self.fingerprint() or code_before != {n: file_hash(self.workspace.resolve(n)) for n in self.workspace.list_files()}:
            raise ValueError('Self-test execution changed original code/tests')
        self.latest['duration_seconds'] = round(time.monotonic() - started, 6)
        save_json(self.root / f'{self.counter:03d}-result.json', self.latest)
        return {**self.latest, 'output': self.latest.get('output', '')[:12000],
                'output_truncated': len(self.latest.get('output', '')) > 12000}
