import importlib.util
import os
from pathlib import Path

path = Path(os.environ["LAB_WORKSPACE"]) / "bounds.py"
spec = importlib.util.spec_from_file_location("submission", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

assert module.clamp(-1, 0, 10) == 0
assert module.clamp(12, 0, 10) == 10
assert module.clamp(5, 0, 10) == 5

print('Public checks passed')
