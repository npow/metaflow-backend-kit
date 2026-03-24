"""
Metaflow backend compliance test runner.

Wraps pytest with the right defaults for running backend compliance tests.

Usage:
    metaflow-backend-test --backend modal
    metaflow-backend-test --backend sandbox --backend-image python:3.11-slim
    metaflow-backend-test --backend modal --supported-caps GPU,TIMEOUT -v

All extra arguments are forwarded to pytest.
"""

import sys


def main() -> None:
    try:
        import pytest
    except ImportError:
        print("error: pytest is required. Install with: pip install pytest", file=sys.stderr)
        sys.exit(1)

    import os

    compliance_dir = os.path.join(os.path.dirname(__file__), "..", "compliance")
    compliance_dir = os.path.normpath(compliance_dir)

    # Forward all CLI args to pytest, prepending the compliance test directory.
    # This lets callers do: metaflow-backend-test --backend modal -v -k retry
    args = [compliance_dir] + sys.argv[1:]
    sys.exit(pytest.main(args))


if __name__ == "__main__":
    main()
