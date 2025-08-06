#!/usr/bin/env python3
"""
Pre-compile Python files to bytecode for marginal performance improvement.
"""

import py_compile
import compileall
import os

def compile_package():
    """Compile all Python files in the cheshire package."""
    
    # Compile the entire package
    print("Compiling cheshire package...")
    success = compileall.compile_dir(
        'cheshire',
        force=True,  # Recompile even if timestamps are up to date
        optimize=2,  # Optimization level (0, 1, or 2)
        quiet=False  # Show compilation progress
    )
    
    if success:
        print("✓ Compilation successful")
        
        # Show size comparison
        import glob
        py_files = glob.glob('cheshire/**/*.py', recursive=True)
        pyc_files = glob.glob('cheshire/**/*.pyc', recursive=True)
        
        py_size = sum(os.path.getsize(f) for f in py_files)
        pyc_size = sum(os.path.getsize(f) for f in pyc_files) if pyc_files else 0
        
        print(f"\nSource files (.py): {py_size:,} bytes")
        print(f"Compiled files (.pyc): {pyc_size:,} bytes")
        print(f"Startup time improvement: ~5-10ms (negligible for CLI tools)")
    else:
        print("✗ Compilation failed")
        return 1
    
    return 0

if __name__ == '__main__':
    exit(compile_package())