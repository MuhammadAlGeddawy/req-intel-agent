#!/usr/bin/env python3
"""
Run script for the Requirements Intelligence Agent.
"""

import sys
import os
import runpy

# Add the current directory to Python path to import src
sys.path.insert(0, os.path.dirname(__file__))

# Execute src.main as a module so its __main__ block runs
runpy.run_module("src.main", run_name="__main__")