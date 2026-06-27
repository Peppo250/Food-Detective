"""
🔬 Food Detective — Root entry point wrapper.
Adds the 'src' directory to Python's search path, then imports and runs the application.
"""
import os
import sys

# Add 'src' directory to sys.path to allow absolute imports of the food_detective package
src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "src"))
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from food_detective.main import run_app

if __name__ == "__main__":
    run_app()
