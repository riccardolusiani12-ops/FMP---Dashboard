"""
Pytest configuration: add dash_app/ to sys.path so `src` is importable.
Run tests from dash_app/ with: pytest tests/
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
