"""Stable JSON-callable entry point for local and isolated execution."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from workshop.service import run
