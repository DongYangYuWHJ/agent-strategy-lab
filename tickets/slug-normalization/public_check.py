from check_client import load_submission
import os
from pathlib import Path

module = load_submission(Path(os.environ["LAB_WORKSPACE"]) / "text.py")

assert module.slug('Hello World') == 'hello-world'
assert module.slug(' Hello,  World! ') == 'hello-world'
assert module.slug('') == ''

print('Public checks passed')
