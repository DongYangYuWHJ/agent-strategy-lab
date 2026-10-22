from check_client import check_stdio_cases
import os
from pathlib import Path
import json

cases = json.loads('[{"input": "3 2\\n#.#\\n..#\\n##.\\n.#\\n#.", "output": "2 2", "testtype": "stdin"}, {"input": "2 1\\n#.\\n##\\n.", "output": "1 2", "testtype": "stdin"}]')
check_stdio_cases(Path(os.environ['LAB_WORKSPACE']) / 'solution.py', cases)
