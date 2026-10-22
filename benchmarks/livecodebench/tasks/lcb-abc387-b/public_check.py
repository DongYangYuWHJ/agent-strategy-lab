from check_client import check_stdio_cases
import os
from pathlib import Path
import json

cases = json.loads('[{"input": "1", "output": "2024", "testtype": "stdin"}, {"input": "11", "output": "2025", "testtype": "stdin"}, {"input": "24", "output": "1929", "testtype": "stdin"}]')
check_stdio_cases(Path(os.environ['LAB_WORKSPACE']) / 'solution.py', cases)
