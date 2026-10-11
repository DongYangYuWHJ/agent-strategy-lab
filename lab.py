"""Run from a checkout without installation: python lab.py demo."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from agent_lab.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
