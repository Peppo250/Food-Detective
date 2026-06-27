import os
import sys

# Add 'src' directory to sys.path to allow absolute imports of the food_detective package during testing
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
