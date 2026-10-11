import importlib.util
import os
from pathlib import Path

path = Path(os.environ["LAB_WORKSPACE"]) / "stats.py"
spec = importlib.util.spec_from_file_location("submission", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

assert module.mean([1, 2, 3]) == 2
try:
    module.mean([])
except ValueError:
    pass
else:
    raise AssertionError('empty input must raise ValueError')

print('Public checks passed')
