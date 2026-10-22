from check_client import check_stdio_cases
import os
from pathlib import Path
import json

cases = json.loads('[{"input": "([])<>()", "output": "Yes", "testtype": "stdin"}, {"input": "([<)]>", "output": "No", "testtype": "stdin"}, {"input": "())", "output": "No", "testtype": "stdin"}]')
check_stdio_cases(Path(os.environ['LAB_WORKSPACE']) / 'solution.py', cases)
