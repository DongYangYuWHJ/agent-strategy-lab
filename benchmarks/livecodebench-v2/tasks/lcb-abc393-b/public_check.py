from check_client import check_stdio_cases
import os
from pathlib import Path
import json

cases = json.loads('[{"input": "AABCC", "output": "2", "testtype": "stdin"}, {"input": "ARC", "output": "0", "testtype": "stdin"}, {"input": "AABAAABBAEDCCCD", "output": "4", "testtype": "stdin"}]')
check_stdio_cases(Path(os.environ['LAB_WORKSPACE']) / 'solution.py', cases)
