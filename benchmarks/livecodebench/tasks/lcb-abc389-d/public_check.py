from check_client import check_stdio_cases
import os
from pathlib import Path
import json

cases = json.loads('[{"input": "2", "output": "5", "testtype": "stdin"}, {"input": "4", "output": "37", "testtype": "stdin"}, {"input": "26", "output": "2025", "testtype": "stdin"}]')
check_stdio_cases(Path(os.environ['LAB_WORKSPACE']) / 'solution.py', cases)
