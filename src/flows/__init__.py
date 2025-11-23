"""Business flow layer.

This package contains all business flow functions with dependency injection.

Note: Importing any module from this package automatically triggers dependency
      registration via the import below. CLI/tests don't need to worry about
      DI initialization timing.
"""

import src.core.container  # noqa: F401 - Trigger dependency registration
