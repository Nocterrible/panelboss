"""Entry point for the logon task; the repo directory is added to the
path before anything is imported, always."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from awaywatch import cli  # noqa

if __name__ == "__main__":
    sys.exit(cli.main())
