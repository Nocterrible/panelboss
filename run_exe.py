"""PyInstaller entry point: the exact same cli.main the venv path runs,
just compiled. The console-free twin of pythonw -m panelboss;
scripts/build_release.ps1 feeds this file to pyinstaller."""

import sys

from panelboss import cli

if __name__ == "__main__":
    sys.exit(cli.main())
