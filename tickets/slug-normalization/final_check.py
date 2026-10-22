from check_client import load_submission
import os
from pathlib import Path

module = load_submission(Path(os.environ["LAB_WORKSPACE"]) / "text.py")

cases = {'---': '', 'A__B': 'a-b', 'A\tB\nC': 'a-b-c', '42': '42', '中文 AI 中文': 'ai', 'One...Two': 'one-two', '  Mixed CASE 123 ': 'mixed-case-123'}
for text, expected in cases.items():
    assert module.slug(text) == expected

print('Final acceptance passed')
