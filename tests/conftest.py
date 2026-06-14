import sys
import os

# Ensure the project root is on sys.path so `import tools` works
# when pytest is run from any directory.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
