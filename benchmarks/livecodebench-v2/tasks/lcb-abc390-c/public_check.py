from check_client import check_stdio_cases
import os
from pathlib import Path
import json

cases = json.loads('[{"input": "3 5\\n.#?#.\\n.?#?.\\n?...?", "output": "Yes", "testtype": "stdin"}, {"input": "3 3\\n?##\\n#.#\\n##?", "output": "No", "testtype": "stdin"}, {"input": "1 1\\n#", "output": "Yes", "testtype": "stdin"}]')
check_stdio_cases(Path(os.environ['LAB_WORKSPACE']) / 'solution.py', cases)
