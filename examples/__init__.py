"""Example scripts; run them with `python -m examples.<name>`."""

import sys

# The examples print α, θ and →. A console that is not UTF-8 (older Windows
# terminals, or output redirected to a file on Windows) would raise
# UnicodeEncodeError; print a replacement character instead.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
