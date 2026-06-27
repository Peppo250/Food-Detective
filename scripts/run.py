#!/usr/bin/env python
"""
Developer utility script to run the Food Detective application directly.
"""
import os
import sys

# Add the 'src' directory to Python's search path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
src_path = os.path.join(project_root, "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from food_detective.main import run_app

if __name__ == "__main__":
    print("[scripts/run] Starting Food Detective...")
    run_app()
