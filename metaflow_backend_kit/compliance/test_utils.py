"""Shared utilities for backend compliance tests."""

import os
from typing import Any, Dict, Optional

from metaflow import Run, Runner


def flows_dir() -> str:
    """Return the path to the flows/ directory bundled with this package."""
    return os.path.join(os.path.dirname(__file__), "flows")


def flow_path(name: str, flows_dir_override: Optional[str] = None) -> str:
    """
    Return the full path to a flow file.

    If flows_dir_override is given, resolve relative to that directory.
    Otherwise, resolve relative to the flows/ directory next to this file.
    """
    base = flows_dir_override or flows_dir()
    if os.path.isabs(name):
        return name
    return os.path.join(base, name)


def run_flow_with_backend(
    flow_path_: str,
    backend_name: str,
    run_kwargs: Optional[Dict[str, Any]] = None,
    **runner_kwargs,
) -> Run:
    """
    Run a flow through a compute backend and return the completed Run.

    Uses Runner with decospecs=[backend_name] to apply the backend decorator
    to every step.  Blocks until the run finishes.

    Parameters
    ----------
    flow_path_ :
        Absolute path to the flow file.
    backend_name :
        The backend decorator name, e.g. ``"modal"``.  Passed as a decospec
        so it is applied to all steps without modifying the flow source.
    run_kwargs :
        Keyword arguments forwarded to ``Runner.run()`` (e.g. ``tags``).
    **runner_kwargs :
        Additional keyword arguments forwarded to the ``Runner`` constructor
        (e.g. ``pylint=False``).

    Returns
    -------
    metaflow.Run
        The completed run object.  Check ``run.successful`` for outcome.
    """
    run_kwargs = run_kwargs or {}
    runner_kwargs.setdefault("pylint", False)

    with Runner(
        flow_path_, decospecs=[backend_name], **runner_kwargs
    ).run(**run_kwargs) as running:
        return running.run
