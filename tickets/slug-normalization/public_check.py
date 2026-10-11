import importlib.util
import os
from pathlib import Path

path = Path(os.environ["LAB_WORKSPACE"]) / "text.py"
spec = importlib.util.spec_from_file_location("submission", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

assert module.slug('Hello World') == 'hello-world'
assert module.slug(' Hello,  World! ') == 'hello-world'
assert module.slug('') == ''

print('Public checks passed')
