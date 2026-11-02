"""Test defaults. Fake drivers use made-up model names with no known prices, so the
suite runs with HUB_UNKNOWN_PRICING=warn; tests of the default (block) set it themselves."""

import os

os.environ.setdefault("HUB_UNKNOWN_PRICING", "warn")
