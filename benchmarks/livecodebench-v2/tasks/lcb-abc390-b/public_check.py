from check_client import check_stdio_cases
import os
from pathlib import Path
import json

cases = json.loads('[{"input": "5\\n3 6 12 24 48", "output": "Yes", "testtype": "stdin"}, {"input": "3\\n1 2 3", "output": "No", "testtype": "stdin"}, {"input": "2\\n10 8", "output": "Yes", "testtype": "stdin"}]')
check_stdio_cases(Path(os.environ['LAB_WORKSPACE']) / 'solution.py', cases)
