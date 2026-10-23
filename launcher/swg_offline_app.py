"""Script entry point for PyInstaller, which cannot run a package's __main__ with relative imports."""

import sys

from swg_offline.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
