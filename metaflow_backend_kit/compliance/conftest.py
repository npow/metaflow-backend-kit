"""
Compliance test fixtures for backend compliance tests.

This conftest is self-contained and designed to be used either:
  - standalone inside metaflow_backend_kit/compliance/
  - dropped into a backend extension's test directory

CLI options
-----------
--backend         (required) Backend decorator name, e.g. ``modal``.
--backend-image   Container image to pass as a decospec argument.
--supported-caps  Comma-separated Cap names the backend declares support for,
                  e.g. ``GPU,TIMEOUT``.  Used to skip optional tests.
--flows-dir       Override the flows/ directory (defaults to package flows/).

Fixtures
--------
backend_name      str — the value of --backend.
backend_image     str or None — the value of --backend-image.
backend_config    BackendConfig — name, image, and supported_caps.
flows_dir         str — path to the flows directory.
"""

import os
from dataclasses import dataclass, field
from typing import Optional, Set

import pytest

from metaflow_backend_kit.capabilities import Cap


# ---------------------------------------------------------------------------
# BackendConfig dataclass
# ---------------------------------------------------------------------------


@dataclass
class BackendConfig:
    """
    Runtime configuration for the backend under test.

    Attributes
    ----------
    name :
        The backend decorator name (e.g. ``"modal"``).
    image :
        Optional container image string.
    supported_caps :
        Set of Cap values the backend declares support for.  Used by
        ``_require_cap`` to skip optional tests.
    """

    name: str
    image: Optional[str] = None
    supported_caps: Set[Cap] = field(default_factory=set)

    def decospec(self) -> str:
        """
        Return the decospec string for Runner.

        If an image was given, returns ``"<name>:image=<image>"``.
        Otherwise returns just the backend name.
        """
        if self.image:
            return "%s:image=%s" % (self.name, self.image)
        return self.name


# ---------------------------------------------------------------------------
# CLI options
# ---------------------------------------------------------------------------


def pytest_addoption(parser):
    parser.addoption(
        "--backend",
        default=None,
        help=(
            "Backend decorator name to test, e.g. 'modal'. "
            "Required for compliance tests."
        ),
    )
    parser.addoption(
        "--backend-image",
        default=None,
        help="Container image to use with the backend decorator.",
    )
    parser.addoption(
        "--supported-caps",
        default=None,
        help=(
            "Comma-separated list of Cap names the backend declares support for, "
            "e.g. 'GPU,TIMEOUT'.  Used to enable optional compliance tests."
        ),
    )
    parser.addoption(
        "--flows-dir",
        default=None,
        help=(
            "Path to the flows/ directory. "
            "Defaults to the flows/ directory bundled with this package."
        ),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def backend_name(request) -> str:
    """The backend decorator name from --backend."""
    name = request.config.getoption("--backend")
    if name is None:
        pytest.skip(
            "No --backend specified. "
            "Run with: pytest metaflow_backend_kit/compliance/ --backend <name>"
        )
    return name


@pytest.fixture(scope="session")
def backend_image(request) -> Optional[str]:
    """The container image from --backend-image, or None."""
    return request.config.getoption("--backend-image")


@pytest.fixture(scope="session")
def backend_config(request, backend_name, backend_image) -> BackendConfig:
    """
    BackendConfig built from CLI options.

    supported_caps is populated from --supported-caps, which accepts a
    comma-separated list of Cap enum names (case-insensitive).

    Example::

        pytest compliance/ --backend modal --supported-caps GPU,TIMEOUT
    """
    raw_caps = request.config.getoption("--supported-caps") or ""
    supported: Set[Cap] = set()
    for token in raw_caps.split(","):
        token = token.strip().upper()
        if not token:
            continue
        try:
            supported.add(Cap[token])
        except KeyError:
            pytest.fail(
                "Unknown capability %r in --supported-caps. "
                "Valid values: %s"
                % (token, ", ".join(c.name for c in Cap))
            )

    return BackendConfig(
        name=backend_name,
        image=backend_image,
        supported_caps=supported,
    )


@pytest.fixture(scope="session")
def flows_dir(request) -> str:
    """
    Path to the flows/ directory.

    Resolved from --flows-dir if given, otherwise falls back to the
    flows/ directory bundled with this package.
    """
    override = request.config.getoption("--flows-dir")
    if override:
        if not os.path.isdir(override):
            raise ValueError(
                "--flows-dir %r does not exist or is not a directory" % override
            )
        return override
    default = os.path.join(os.path.dirname(__file__), "flows")
    return default
