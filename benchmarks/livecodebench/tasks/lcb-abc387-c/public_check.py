from check_client import check_stdio_cases
import os
from pathlib import Path
import json

cases = json.loads('[{"input": "97 210", "output": "6", "testtype": "stdin"}, {"input": "1000 9999", "output": "2025", "testtype": "stdin"}, {"input": "252509054433933519 760713016476190692", "output": "221852052834757", "testtype": "stdin"}]')
check_stdio_cases(Path(os.environ['LAB_WORKSPACE']) / 'solution.py', cases)
