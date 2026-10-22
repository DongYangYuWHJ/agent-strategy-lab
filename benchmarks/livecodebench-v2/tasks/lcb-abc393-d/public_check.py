from check_client import check_stdio_cases
import os
from pathlib import Path
import json

cases = json.loads('[{"input": "7\\n0101001", "output": "3", "testtype": "stdin"}, {"input": "3\\n100", "output": "0", "testtype": "stdin"}, {"input": "10\\n0101001001", "output": "7", "testtype": "stdin"}]')
check_stdio_cases(Path(os.environ['LAB_WORKSPACE']) / 'solution.py', cases)
