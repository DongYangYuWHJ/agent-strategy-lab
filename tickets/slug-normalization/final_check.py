import importlib.util
import os
from pathlib import Path

path = Path(os.environ["LAB_WORKSPACE"]) / "text.py"
spec = importlib.util.spec_from_file_location("submission", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

cases = {'---': '', 'A__B': 'a-b', 'A\tB\nC': 'a-b-c', '42': '42', '中文 AI 中文': 'ai', 'One...Two': 'one-two', '  Mixed CASE 123 ': 'mixed-case-123'}
for text, expected in cases.items():
    assert module.slug(text) == expected

print('Final acceptance passed')
