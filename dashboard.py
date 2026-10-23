"""Run with: uv run streamlit run dashboard.py"""

import argparse
from pathlib import Path

from centauro_atlas_bridge.dashboard.app import main

parser = argparse.ArgumentParser()
parser.add_argument("--state-dir", type=Path, default=None)
args = parser.parse_args()
main(args.state_dir)
