from check_client import check_stdio_cases
import os
from pathlib import Path
import json

cases = json.loads('[{"input": "6\\n2\\n1 4\\n1 3\\n2\\n2\\n2", "output": "0\\n3\\n4\\n0", "testtype": "stdin"}, {"input": "5\\n2\\n2\\n2\\n2\\n2", "output": "0\\n0\\n0\\n0\\n0", "testtype": "stdin"}]')
check_stdio_cases(Path(os.environ['LAB_WORKSPACE']) / 'solution.py', cases)
