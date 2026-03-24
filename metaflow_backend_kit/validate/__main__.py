"""
Static validator for Metaflow compute backend extensions.

Analyzes Python source files for common implementation mistakes before CI runs.
Checks StepDecorator implementations for the 12 most common pitfalls.

Usage:
    python -m metaflow_backend_kit.validate path/to/my_backend/
    metaflow-backend-validate path/to/my_backend/
    metaflow-backend-validate .   # scans current directory
"""

import os
import re
import sys
from collections import namedtuple

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

_Check = namedtuple("_Check", ["name", "passed", "detail", "hint"], defaults=[None, None])

# Sentinel values for the three possible outcomes
PASS = "pass"
WARN = "warn"
FAIL = "fail"

# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------


def _load_files(paths):
    """Return a dict mapping filepath -> source string for all given paths.

    If a path is a directory, walks it recursively for *.py files.
    If a path is a file, includes it directly.
    """
    files = {}
    for path in paths:
        if os.path.isdir(path):
            for dirpath, _dirnames, filenames in os.walk(path):
                for fname in filenames:
                    if fname.endswith(".py"):
                        full = os.path.join(dirpath, fname)
                        try:
                            with open(full, "r", encoding="utf-8", errors="replace") as fh:
                                files[full] = fh.read()
                        except OSError:
                            pass
        elif os.path.isfile(path) and path.endswith(".py"):
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as fh:
                    files[path] = fh.read()
            except OSError:
                pass
    return files


def _strip_comments(source):
    """Return source with # comment text and docstrings removed.

    Keeps line structure intact (replaces matched text with whitespace of the
    same length) so that line-number-sensitive patterns still work.
    """
    # Remove triple-quoted strings (docstrings and multi-line string literals)
    source = re.sub(r'"""[\s\S]*?"""', lambda m: " " * len(m.group()), source)
    source = re.sub(r"'''[\s\S]*?'''", lambda m: " " * len(m.group()), source)
    # Remove single-line # comments
    source = re.sub(r"#[^\n]*", "", source)
    return source


def _find_in_any_file(files, pattern, strip_comments=False):
    """Search pattern across all files.

    Returns (filename, match) for the first file that matches, or None.
    When strip_comments=True, comment text is removed before matching so
    that patterns mentioned in comments do not trigger false positives.
    Always uses re.MULTILINE so ^ anchors match line starts.
    """
    for filename, source in files.items():
        text = _strip_comments(source) if strip_comments else source
        m = re.search(pattern, text, re.MULTILINE)
        if m:
            return (filename, m)
    return None


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def _check_extension_registration(files):
    """Check 1: Extension registration exists.

    The extension must expose STEP_DECORATORS_DESC so Metaflow can discover
    the decorator.  This lives in plugins/__init__.py or a mfextinit_*.py
    module.
    """
    name = "extension registration exists"

    for filepath, source in files.items():
        basename = os.path.basename(filepath)
        is_plugins_init = (
            basename == "__init__.py"
            and os.path.basename(os.path.dirname(filepath)) == "plugins"
        )
        is_mfextinit = re.match(r"mfextinit_.+\.py$", basename)
        if (is_plugins_init or is_mfextinit) and "STEP_DECORATORS_DESC" in source:
            return _Check(name=name, passed=PASS)

    return _Check(
        name=name,
        passed=FAIL,
        detail="No extension registration found.",
        hint="Create plugins/__init__.py with STEP_DECORATORS_DESC = [(...)]",
    )


def _check_supported_capabilities(files):
    """Check 2: SUPPORTED_CAPABILITIES declared on the decorator class.

    Every backend decorator must advertise which Cap values it implements so
    the compliance suite knows what to test.
    """
    name = "SUPPORTED_CAPABILITIES declared"

    if _find_in_any_file(files, r"\bSUPPORTED_CAPABILITIES\b", strip_comments=True):
        return _Check(name=name, passed=PASS)

    return _Check(
        name=name,
        passed=FAIL,
        detail="SUPPORTED_CAPABILITIES not declared on decorator class.",
        hint="Add: SUPPORTED_CAPABILITIES = REQUIRED | {Cap.GPU}  # add your optional caps",
    )


def _check_retry_count_not_hardcoded(files):
    """Check 3a: retry_count must not be hardcoded to zero.

    Most backends are 1-indexed (first attempt == 1).  Converting with
    max(0, attempt - 1) is required; a bare retry_count=0 silently disables
    all retry logic.
    """
    name = "retry_count not hardcoded"

    # Use a negative lookahead (?!=) to reject == while consuming no extra
    # character, so that both "retry_count=0" and "retry_count = 0" match.
    # Strip comments so that mentions in docstrings/comments don't fire.
    match = _find_in_any_file(files, r"\bretry_count\s*=(?!=)\s*0\b", strip_comments=True)
    if match:
        filepath, m = match
        return _Check(
            name=name,
            passed=FAIL,
            detail="retry_count hardcoded to 0. Derive from Metaflow's retry_count parameter.",
            hint="See docs/pitfalls/retry-count-indexing.md",
        )

    return _Check(name=name, passed=PASS)


def _check_retry_count_not_decremented(files):
    """Check 3b: retry_count must not be decremented by 1.

    If the backend uses a 1-indexed counter (first attempt == 1) the correct
    conversion is max(0, backend_counter - 1).  Subtracting 1 from Metaflow's
    already-0-indexed retry_count produces -1 on the first attempt.
    """
    name = "retry_count not decremented"

    match = _find_in_any_file(files, r"\bretry_count\s*-\s*1\b", strip_comments=True)
    if match:
        return _Check(
            name=name,
            passed=FAIL,
            detail=(
                "retry_count - 1 found. Metaflow's retry_count is already 0-indexed; "
                "subtracting 1 produces -1 on the first attempt."
            ),
            hint="See docs/pitfalls/retry-count-indexing.md",
        )

    return _Check(name=name, passed=PASS)


def _check_runtime_environment_set(files):
    """Check 4: METAFLOW_RUNTIME_ENVIRONMENT must be set in the container env.

    Metaflow uses this variable to distinguish execution contexts (local,
    batch, kubernetes, …).  Without it the step runs as if executing locally.
    """
    name = "METAFLOW_RUNTIME_ENVIRONMENT set"

    if _find_in_any_file(files, r"METAFLOW_RUNTIME_ENVIRONMENT", strip_comments=True):
        return _Check(name=name, passed=PASS)

    return _Check(
        name=name,
        passed=FAIL,
        detail="METAFLOW_RUNTIME_ENVIRONMENT not set in container env.",
        hint="Add METAFLOW_RUNTIME_ENVIRONMENT = '{name}' to the env dict in runtime_step_cli()",
    )


def _check_conda_remote_commands(files):
    """Check 5: Conda remote command aliases must be patched when supports_conda is True.

    The submitting machine may be macOS/arm64 while the remote is linux-64.
    Without patching _CONDA_REMOTE_COMMANDS the resolver downloads the wrong
    package architectures.
    """
    name = "conda remote commands patched"

    conda_enabled = _find_in_any_file(files, r"supports_conda_environment\s*=\s*True")
    if not conda_enabled:
        # Not applicable — skip with a pass
        return _Check(name=name, passed=PASS)

    if _find_in_any_file(files, r"_ensure_conda_remote_command_aliases"):
        return _Check(name=name, passed=PASS)

    return _Check(
        name=name,
        passed=FAIL,
        detail="supports_conda_environment=True but _ensure_conda_remote_command_aliases() never called.",
        hint=(
            "Call self._ensure_conda_remote_command_aliases(environment) in step_init(). "
            "See docs/pitfalls/conda-remote-commands.md"
        ),
    )


def _check_target_platform(files):
    """Check 6: target_platform must be set when supports_conda is True.

    Conda package resolution is platform-specific.  Without an explicit
    target_platform the resolver uses the submitter's OS, which fails when
    deploying from macOS to Linux containers.
    """
    name = "target_platform set for conda"

    conda_enabled = _find_in_any_file(files, r"supports_conda_environment\s*=\s*True")
    if not conda_enabled:
        return _Check(name=name, passed=PASS)

    if _find_in_any_file(files, r"\btarget_platform\b"):
        return _Check(name=name, passed=PASS)

    return _Check(
        name=name,
        passed=FAIL,
        detail="supports_conda_environment=True but target_platform never set.",
        hint=(
            "Add _default_target_platform() that returns 'linux-64' or detects arm64. "
            "See docs/pitfalls/conda-remote-commands.md"
        ),
    )


def _check_credentials_import_time(files):
    """Check 7: Credentials should be captured at import time (WARN only).

    Auth environment variables (AWS_*, AZURE_*, GOOGLE_*) may be mutated or
    cleared later in the process.  Capturing them at module load time makes
    the decorator resilient to such mutations.

    This check emits a warning rather than a hard failure because the pattern
    is somewhat implementation-specific.
    """
    name = "credentials captured at import time"

    # Look for a module-level dict/variable capturing env vars.
    # Accepted patterns:
    #   _INITIAL_<something> = ...
    #   {k: os.environ.get(k) ...}  at module level (outside a def/class)
    # Match _INITIAL_FOO = ... or _INITIAL_FOO: SomeType = ...
    if _find_in_any_file(files, r"^_INITIAL_\w+\s*(?::[^=]*)?\s*=", ) or _find_in_any_file(
        files, r"^\w+\s*=\s*\{[^}]*os\.environ"
    ):
        return _Check(name=name, passed=PASS)

    return _Check(
        name=name,
        passed=WARN,
        detail="No module-level credential capture found.",
        hint=(
            "Capture auth env vars at module level to avoid env mutation issues. "
            "See docs/pitfalls/credentials-import-time.md"
        ),
    )


def _check_resources_merge(files):
    """Check 8: @resources decorator params must be merged with max().

    When a user annotates a step with both @resources and your decorator,
    your decorator must honour the more generous of the two values.  Ignoring
    @resources silently under-provisions the container.
    """
    name = "@resources merging implemented"

    resources_ref = _find_in_any_file(
        files,
        r'(resources_deco|"resources"|resource_defaults|\bresources\b.*step_init)',
        strip_comments=True,
    )
    if resources_ref:
        return _Check(name=name, passed=PASS)

    return _Check(
        name=name,
        passed=FAIL,
        detail="@resources merging not implemented. Decorator params must be merged with @resources using max().",
        hint="See docs/pitfalls/resources-merge.md",
    )


def _check_infra_exit_code(files):
    """Check 9: Infrastructure failures must exit with METAFLOW_EXIT_DISALLOW_RETRY.

    When provisioning, authentication, or network setup fails it is wrong to
    let Metaflow's @retry decorator burn retry attempts on non-user-code
    failures.  METAFLOW_EXIT_DISALLOW_RETRY signals the orchestrator to abort
    immediately.
    """
    name = "METAFLOW_EXIT_DISALLOW_RETRY used"

    if _find_in_any_file(files, r"METAFLOW_EXIT_DISALLOW_RETRY", strip_comments=True):
        return _Check(name=name, passed=PASS)

    return _Check(
        name=name,
        passed=FAIL,
        detail="METAFLOW_EXIT_DISALLOW_RETRY never used. Infrastructure failures must not be retried.",
        hint=(
            "Import from metaflow.exception and call "
            "sys.exit(METAFLOW_EXIT_DISALLOW_RETRY) for provisioning/auth failures."
        ),
    )


def _check_metadata_sync(files):
    """Check 10: Local metadata must be synced back to the service (WARN only).

    Steps write metadata (timestamps, tags, attempt IDs) locally inside the
    container.  Without an explicit sync call that data never reaches the
    Metaflow service, breaking the UI and downstream dependency resolution.
    """
    name = "metadata sync present"

    if _find_in_any_file(
        files,
        r"(_replay_task_metadata_to_service|sync_local_metadata)",
        strip_comments=True,
    ):
        return _Check(name=name, passed=PASS)

    # task_finished that does more than pass
    for source in files.values():
        m = re.search(
            r"def task_finished\s*\([^)]*\)\s*:(.*?)(?=\ndef |\Z)",
            source,
            re.DOTALL,
        )
        if m:
            body = m.group(1)
            # Strip comments and blank lines; if anything substantial remains
            # beyond a bare `pass` it counts as an implementation.
            stripped = re.sub(r"#[^\n]*", "", body).strip()
            if stripped and stripped != "pass":
                return _Check(name=name, passed=PASS)

    return _Check(
        name=name,
        passed=WARN,
        detail="No metadata sync found. Local metadata may not reach the service.",
        hint="See docs/pitfalls/metadata-sync.md",
    )


def _check_task_id_not_hardcoded(files):
    """Check 11: task_id must not be hardcoded to 1.

    Some copy-paste examples hard-code --task-id 1 in the step command.
    For single-node flows this appears to work but breaks @foreach and
    @parallel steps that run multiple tasks with distinct IDs.
    """
    name = "task_id not hardcoded"

    match = _find_in_any_file(files, r"(task_id\s*=\s*1\b|--task-id\s+1\b)", strip_comments=True)
    if match:
        return _Check(
            name=name,
            passed=FAIL,
            detail="task_id hardcoded to 1 in step command.",
            hint="Use the task_id parameter from runtime_task_created().",
        )

    return _Check(name=name, passed=PASS)


def _check_code_package_not_local(files):
    """Check 12: Code package must use a datastore URL, not a local path (WARN only).

    If the code package path points to /tmp/ or another local directory it
    will be inaccessible from the remote container.  The correct approach is
    to upload the package to the configured datastore and pass the URL.
    """
    name = "code package uses datastore URL"

    # Positive signal: package_url() call — implementation looks correct
    if _find_in_any_file(files, r"package\.package_url\(\)"):
        return _Check(name=name, passed=PASS)

    # Negative signal: /tmp/ path appearing near code-package keywords
    for source in files.values():
        m = re.search(r"(code.?package|package_path|package_url)[^\n]{0,120}/tmp/", source)
        if m:
            return _Check(
                name=name,
                passed=WARN,
                detail="Possible local filesystem path in code package.",
                hint=(
                    "Ensure you use the datastore URL (package.package_url()). "
                    "See docs/pitfalls/code-package-locality.md"
                ),
            )

    # No clear signal either way — optimistically pass
    return _Check(name=name, passed=PASS)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _check_env_propagation(files):
    """Check 13: Auth environment variables must be forwarded to the remote task.

    Credentials captured at import time (_INITIAL_AUTH_ENV pattern) must be
    explicitly included in the container's environment dict.  If env vars are
    not forwarded, the remote container cannot authenticate with the backend.
    """
    name = "auth env vars forwarded to container"

    # Accept any reference to _AUTH_VARS or _INITIAL_AUTH_ENV in a context
    # that implies forwarding (not just declaration).
    if _find_in_any_file(
        files,
        r"(_INITIAL_AUTH_ENV|_AUTH_VARS)",
        strip_comments=True,
    ):
        return _Check(name=name, passed=PASS)

    return _Check(
        name=name,
        passed=WARN,
        detail="No credential forwarding pattern found.",
        hint=(
            "Capture auth env vars at module level in _INITIAL_AUTH_ENV and inject them "
            "into the container env in runtime_step_cli(). "
            "See docs/pitfalls/credentials-import-time.md"
        ),
    )


def _check_code_package_uploaded(files):
    """Check 14: Code package must be uploaded via the datastore before dispatch.

    Metaflow passes the code package blob to the decorator in runtime_init().
    The decorator must upload it exactly once (use a class-level guard) so the
    remote container can download it via the URL.  Missing upload causes the
    remote task to fail immediately with a missing-package error.
    """
    name = "code package uploaded via datastore"

    if _find_in_any_file(
        files,
        r"(save_data|_save_package_once|package_url\s*=|\.blob)",
        strip_comments=True,
    ):
        return _Check(name=name, passed=PASS)

    return _Check(
        name=name,
        passed=WARN,
        detail="No code package upload detected.",
        hint=(
            "Implement _save_package_once() using flow_datastore.save_data() "
            "and store the result in package_url/package_sha class variables. "
            "See docs/pitfalls/code-package.md"
        ),
    )


def _check_datastore_access(files):
    """Check 15: Datastore access must not use local filesystem paths.

    Remote tasks run in isolated containers.  Any datastore interaction that
    references a local path (/tmp/, relative paths, os.getcwd()) will fail.
    The decorator must pass the configured datastore URL as the code-package
    source, not a local path.
    """
    name = "datastore access uses remote-safe paths"

    # Warn if we see local path patterns used together with code-package keywords.
    for source in files.values():
        m = re.search(
            r"(code_package|package_url|package_sha)[^\n]{0,200}(os\.getcwd|/tmp/|\./)",
            source,
        )
        if m:
            return _Check(
                name=name,
                passed=WARN,
                detail="Possible local filesystem path used with code-package.",
                hint=(
                    "Ensure code-package paths are datastore URLs, not local paths. "
                    "See docs/pitfalls/code-package-locality.md"
                ),
            )

    return _Check(name=name, passed=PASS)


_ALL_CHECKS = [
    _check_extension_registration,
    _check_supported_capabilities,
    _check_retry_count_not_hardcoded,
    _check_retry_count_not_decremented,
    _check_runtime_environment_set,
    _check_conda_remote_commands,
    _check_target_platform,
    _check_credentials_import_time,
    _check_env_propagation,
    _check_resources_merge,
    _check_infra_exit_code,
    _check_metadata_sync,
    _check_code_package_uploaded,
    _check_datastore_access,
    _check_task_id_not_hardcoded,
    _check_code_package_not_local,
]


def run_checks(files):
    """Run all checks against the loaded file dict and return a list of _Check results."""
    return [check(files) for check in _ALL_CHECKS]


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

# Terminal colour helpers (disabled automatically when not a tty)
def _supports_color():
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _c(code, text):
    if _supports_color():
        return f"\033[{code}m{text}\033[0m"
    return text


def _green(t):
    return _c("32", t)


def _yellow(t):
    return _c("33", t)


def _red(t):
    return _c("31", t)


def _bold(t):
    return _c("1", t)


_RULE = "━" * 40


def print_results(target, results):
    """Pretty-print validation results to stdout."""
    print()
    print(_bold(f"Validating: {os.path.abspath(target)}"))
    print(_RULE)
    print()

    for check in results:
        if check.passed == PASS:
            icon = _green("✓")
            line = f"{icon}  {check.name}"
            print(line)
        elif check.passed == WARN:
            icon = _yellow("⚠")
            line = f"{icon}  {check.name}"
            print(line)
            if check.detail:
                print(f"   {_yellow(check.detail)}")
            if check.hint:
                print(f"   → {check.hint}")
        else:  # FAIL
            icon = _red("✗")
            line = f"{icon}  {check.name}"
            print(line)
            if check.detail:
                print(f"   {_red(check.detail)}")
            if check.hint:
                print(f"   → {check.hint}")

    n_pass = sum(1 for c in results if c.passed == PASS)
    n_warn = sum(1 for c in results if c.passed == WARN)
    n_fail = sum(1 for c in results if c.passed == FAIL)

    print()
    print(_RULE)

    summary_parts = [_green(f"{n_pass} passed")]
    if n_warn:
        summary_parts.append(_yellow(f"{n_warn} warned"))
    if n_fail:
        summary_parts.append(_red(f"{n_fail} failed"))

    print(_bold("Results: ") + ", ".join(summary_parts))
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate a Metaflow compute backend extension.",
        epilog=(
            "Exit code 0 when all checks pass or warn. "
            "Exit code 1 when any check fails."
        ),
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Directory or .py file to validate (default: current directory)",
    )
    args = parser.parse_args()

    target = args.path
    if not os.path.exists(target):
        print(f"error: path not found: {target}", file=sys.stderr)
        sys.exit(2)

    files = _load_files([target])

    if not files:
        print(f"error: no Python source files found under: {target}", file=sys.stderr)
        sys.exit(2)

    results = run_checks(files)
    print_results(target, results)

    if any(c.passed == FAIL for c in results):
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
