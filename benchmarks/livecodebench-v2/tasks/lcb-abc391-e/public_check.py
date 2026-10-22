from check_client import check_stdio_cases
import os
from pathlib import Path
import json

cases = json.loads('[{"input": "2\\n010011101", "output": "1", "testtype": "stdin"}, {"input": "1\\n000", "output": "2", "testtype": "stdin"}]')
check_stdio_cases(Path(os.environ['LAB_WORKSPACE']) / 'solution.py', cases)
