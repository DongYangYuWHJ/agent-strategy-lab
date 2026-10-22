from check_client import load_submission
import os
from pathlib import Path

module = load_submission(Path(os.environ["LAB_WORKSPACE"]) / "stats.py")

assert module.mean([1, 2, 3]) == 2
try:
    module.mean([])
except ValueError:
    pass
else:
    raise AssertionError('empty input must raise ValueError')

print('Public checks passed')
