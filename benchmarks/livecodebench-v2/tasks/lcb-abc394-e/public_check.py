from check_client import check_stdio_cases
import os
from pathlib import Path
import json

cases = json.loads('[{"input": "4\\nab--\\n--b-\\n---a\\nc---", "output": "0 1 2 4\\n-1 0 1 -1\\n3 -1 0 1\\n1 -1 -1 0", "testtype": "stdin"}, {"input": "5\\nus---\\n-st--\\n--s--\\nu--s-\\n---ts", "output": "0 1 3 -1 -1\\n-1 0 1 -1 -1\\n-1 -1 0 -1 -1\\n1 3 -1 0 -1\\n-1 -1 5 1 0", "testtype": "stdin"}]')
check_stdio_cases(Path(os.environ['LAB_WORKSPACE']) / 'solution.py', cases)
