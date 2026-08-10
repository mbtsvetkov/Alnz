"""Thin launcher: run the dbt_yaml_generator package from procs\\cpnc.

Equivalent to `python -m dbt_yaml_generator`, callable as
`python procs/cpnc/run_yaml_generator.py [args...]` from anywhere.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dbt_yaml_generator.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
