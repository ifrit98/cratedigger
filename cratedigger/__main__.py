"""Entry point for `python -m cratedigger`, which is how the toolkit runs
from a clone with nothing installed."""
import sys

from cratedigger.cli import main

if __name__ == "__main__":
    sys.exit(main())
