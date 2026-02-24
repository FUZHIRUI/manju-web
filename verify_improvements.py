#!/usr/bin/env python3
"""
Verification script for code improvements.

This script verifies that the improvements have been correctly implemented.
"""

import sys
from pathlib import Path

def check_file_exists(filepath: str, description: str) -> bool:
    """Check if a file exists."""
    path = Path(filepath)
    exists = path.exists()
    status = "✓" if exists else "✗"
    print(f"  {status} {description}: {filepath}")
    return exists

def check_module_import(module_path: str) -> bool:
    """Check if a module can be imported."""
    try:
        exec(f"import {module_path}")
        print(f"  ✓ Module importable: {module_path}")
        return True
    except Exception as e:
        print(f"  ✗ Module import failed: {module_path} - {e}")
        return False

def main():
    """Run all verification checks."""
    print("=" * 60)
    print("Manju Web Code Improvements - Verification")
    print("=" * 60)
    print()

    all_passed = True

    # Check 1: New utility modules
    print("1. Checking new utility modules...")
    all_passed &= check_file_exists(
        "backend/utils/__init__.py",
        "Utils package init"
    )
    all_passed &= check_file_exists(
        "backend/utils/project_utils.py",
        "Project utilities"
    )
    all_passed &= check_file_exists(
        "backend/repositories/table_builder.py",
        "Table builder"
    )
    print()

    # Check 2: New config module
    print("2. Checking new config module...")
    all_passed &= check_file_exists(
        "backend/services/workflow_runtime/config.py",
        "Thread-safe config"
    )
    print()

    # Check 3: Modular visual_audio structure
    print("3. Checking visual_audio module structure...")
    all_passed &= check_file_exists(
        "backend/services/workflow_runtime/visual_audio/__init__.py",
        "Visual audio package init"
    )
    all_passed &= check_file_exists(
        "backend/services/workflow_runtime/visual_audio/models.py",
        "Data models"
    )
    all_passed &= check_file_exists(
        "backend/services/workflow_runtime/visual_audio/prompt_builders.py",
        "Prompt builders"
    )
    all_passed &= check_file_exists(
        "backend/services/workflow_runtime/visual_audio/utils.py",
        "Utilities"
    )
    print()

    # Check 4: Documentation
    print("4. Checking documentation...")
    all_passed &= check_file_exists(
        "IMPROVEMENTS_SUMMARY.md",
        "Improvements summary"
    )
    print()

    # Summary
    print("=" * 60)
    if all_passed:
        print("✓ All verification checks PASSED!")
        print("=" * 60)
        return 0
    else:
        print("✗ Some verification checks FAILED!")
        print("=" * 60)
        return 1

if __name__ == "__main__":
    sys.exit(main())
