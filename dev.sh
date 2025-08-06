#!/usr/bin/env python3
"""
Development runner for Cheshire.
This allows running the app directly without installation.
"""

import sys
import os

# Add the project directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import and run the main function
from cheshire.main import main

if __name__ == '__main__':
    main()