"""Run the toolkit in the app directory with the same AWS profile as deployment."""

import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

root = Path(__file__).resolve().parent
load_dotenv(root / ".env")
raise SystemExit(subprocess.call(
    [str(Path(sys.executable).with_name("agentcore")), *sys.argv[1:]],
    cwd=root / "app",
    env=os.environ.copy(),
))
