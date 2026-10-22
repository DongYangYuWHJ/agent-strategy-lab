from check_client import check_stdio_cases
import os
from pathlib import Path
import json

cases = json.loads('[{"input": "20 25", "output": "2025", "testtype": "stdin"}, {"input": "30 25", "output": "3025", "testtype": "stdin"}, {"input": "45 11", "output": "3136", "testtype": "stdin"}, {"input": "2025 1111", "output": "9834496", "testtype": "stdin"}]')
check_stdio_cases(Path(os.environ['LAB_WORKSPACE']) / 'solution.py', cases)
