from check_client import load_submission
import os
from pathlib import Path

module = load_submission(Path(os.environ["LAB_WORKSPACE"]) / "stats.py")

for values in [[-4, -2, 0], [0.25, 0.5, 0.75], [17], [0, 0, 0]]:
    original = list(values)
    assert module.mean(values) == sum(values) / len(values)
    assert values == original
try:
    module.mean(())
except ValueError:
    pass
else:
    raise AssertionError('empty tuple must raise ValueError')

print('Final acceptance passed')
