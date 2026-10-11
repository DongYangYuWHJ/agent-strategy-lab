import importlib.util
import os
from pathlib import Path

path = Path(os.environ["LAB_WORKSPACE"]) / "bounds.py"
spec = importlib.util.spec_from_file_location("submission", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

for lower, upper in [(-10, -2), (0, 0), (-1.5, 2.5), (100, 101)]:
    for value in [lower - 1, lower, (lower + upper) / 2, upper, upper + 1]:
        assert module.clamp(value, lower, upper) == max(lower, min(value, upper))
try:
    module.clamp(3, 10, 0)
except ValueError:
    pass
else:
    raise AssertionError('invalid bounds must raise ValueError')

print('Final acceptance passed')
