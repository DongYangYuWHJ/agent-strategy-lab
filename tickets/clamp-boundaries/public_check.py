from check_client import load_submission
import os
from pathlib import Path

module = load_submission(Path(os.environ["LAB_WORKSPACE"]) / "bounds.py")

assert module.clamp(-1, 0, 10) == 0
assert module.clamp(12, 0, 10) == 10
assert module.clamp(5, 0, 10) == 5

print('Public checks passed')
