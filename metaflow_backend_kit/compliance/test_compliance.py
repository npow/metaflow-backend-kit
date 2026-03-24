"""
Backend compliance tests.

Each test is a targeted regression for a specific bug that new backend
implementations consistently get wrong. The WHY comment explains the
root cause.

Run against a specific backend:
    pytest metaflow_backend_kit/compliance/ --backend modal -v

All tests use Runner with decospecs to apply the backend decorator.
"""

import os
import pytest

from metaflow_backend_kit.capabilities import Cap, OPTIONAL

from .conftest import BackendConfig
from .test_utils import flow_path, run_flow_with_backend


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_cap(backend_config: BackendConfig, cap: Cap) -> None:
    """
    Skip the current test if cap is OPTIONAL and not in backend_config.supported_caps.

    REQUIRED capabilities are never skipped — the test will fail if the
    implementation is broken.
    """
    if cap not in OPTIONAL:
        return
    if cap not in backend_config.supported_caps:
        pytest.skip(
            "%s: %s does not declare %s support"
            % (cap.name, backend_config.name, cap.name)
        )


# ---------------------------------------------------------------------------
# test_env_vars_reach_container
#
# WHY: Backends must forward METAFLOW_* vars. Without this, flow.current.*
# is empty/wrong inside steps because the runtime reads these vars to
# populate current.user, current.flow_name, etc.
#
# Capability: Cap.ENV_PROPAGATION (REQUIRED)
# ---------------------------------------------------------------------------


def test_env_vars_reach_container(backend_config, flows_dir):
    """METAFLOW_* environment variables must reach the remote container."""
    run = run_flow_with_backend(
        flow_path("env_flow.py", flows_dir),
        backend_config.decospec(),
    )

    assert run.successful, (
        "EnvFlow failed. Check that METAFLOW_* vars are forwarded to the container."
    )
    assert run["read_env"].task.data.metaflow_user == os.environ.get(
        "METAFLOW_USER"
    ), (
        "metaflow_user artifact does not match METAFLOW_USER from the submitter. "
        "The backend likely strips METAFLOW_* vars from the container environment."
    )


# ---------------------------------------------------------------------------
# test_retry_count_zero_on_first_attempt
#
# WHY: Backend attempt counters are 1-indexed. The first execution must see
# retry_count=0, not 1. Backends that pass the raw attempt counter directly
# (without subtracting 1) cause every step to behave as if it is already
# on its second attempt.
#
# Capability: Cap.RETRY_COUNT (REQUIRED)
# ---------------------------------------------------------------------------


def test_retry_count_zero_on_first_attempt(backend_config, flows_dir):
    """retry_count must be 0 on the very first execution attempt."""
    run = run_flow_with_backend(
        flow_path("retry_flow.py", flows_dir),
        backend_config.decospec(),
    )

    assert run.successful, "RetryFlow failed unexpectedly."
    first_attempt_retry_count = (
        run["store_retry_count"].task.data.first_attempt_retry_count
    )
    assert first_attempt_retry_count == 0, (
        "Expected retry_count=0 on first attempt, got %r. "
        "The backend may be passing a 1-indexed attempt counter directly. "
        "Use max(0, counter - 1) to convert." % first_attempt_retry_count
    )
    second_attempt_retry_count = (
        run["store_retry_count"].task.data.second_attempt_retry_count
    )
    assert second_attempt_retry_count == 1, (
        "Expected retry_count=1 on second attempt, got %r. "
        "retry_count must increment by 1 per retry." % second_attempt_retry_count
    )


# ---------------------------------------------------------------------------
# test_retry_count_increments
#
# WHY: If retry_count is always 0, @retry can't work — the step always
# looks like the first attempt and never sees it is on a retry. This test
# forces a step to fail on attempt 0 and only succeed on attempt 1.
#
# Capability: Cap.RETRY_COUNT (REQUIRED)
# ---------------------------------------------------------------------------


def test_retry_count_increments(backend_config, flows_dir):
    """retry_count must increment across retries so @retry logic can function."""
    run = run_flow_with_backend(
        flow_path("retry_flow.py", flows_dir),
        backend_config.decospec(),
    )

    assert run.successful, (
        "RetryFlow failed. If flaky_step never succeeded, retry_count may be "
        "always 0 so the deliberate failure on attempt 0 repeats forever."
    )
    succeeded_on_attempt = run["flaky_step"].task.data.succeeded_on_attempt
    assert succeeded_on_attempt == 1, (
        "Expected flaky_step to succeed on attempt 1, got succeeded_on_attempt=%r. "
        "retry_count is not incrementing across retries." % succeeded_on_attempt
    )


# ---------------------------------------------------------------------------
# test_artifact_readable_after_step
#
# WHY: The container must write artifacts to the configured datastore, not to
# local disk. If the backend runs in a container without the submitter's
# filesystem, local writes are invisible to the client after the step.
#
# Capability: Cap.DATASTORE_ACCESS (REQUIRED)
# ---------------------------------------------------------------------------


def test_artifact_readable_after_step(backend_config, flows_dir):
    """Artifacts written inside the container must be readable via the client."""
    run = run_flow_with_backend(
        flow_path("artifact_flow.py", flows_dir),
        backend_config.decospec(),
    )

    assert run.successful, "ArtifactFlow failed."
    result = run["write_artifact"].task.data.result
    assert result == 42, (
        "Expected result=42 from write_artifact step, got %r. "
        "The artifact may have been written to local disk rather than "
        "the configured datastore." % result
    )


# ---------------------------------------------------------------------------
# test_infra_failure_no_retry
#
# WHY: Provisioning failures (OOM killed by the scheduler, spot preemption,
# node eviction) must use METAFLOW_EXIT_DISALLOW_RETRY so Metaflow does not
# consume the user's @retry budget on infrastructure failures. Testing this
# automatically requires a way to deliberately trigger a provisioning failure,
# which is backend-specific and environment-dependent.
#
# Capability: Cap.INFRA_EXIT_CODE (REQUIRED)
# ---------------------------------------------------------------------------


def test_infra_failure_no_retry(backend_config, flows_dir):
    """Infrastructure failures must not consume the user's @retry budget."""
    if not os.environ.get("MBK_TEST_INFRA_FAILURE"):
        pytest.skip(
            "Set MBK_TEST_INFRA_FAILURE=1 to enable this test. "
            "INFRA_EXIT_CODE must be tested manually: trigger a provisioning failure "
            "(e.g. request more memory than available, or simulate a spot preemption) "
            "and verify that the step is marked as failed without retrying. "
            "Check that the exit code is METAFLOW_EXIT_DISALLOW_RETRY."
        )
    # Backend-specific implementation: set up a flow that triggers a provisioning
    # failure, run it with @retry(times=2), and verify it fails without retrying.
    pytest.fail(
        "MBK_TEST_INFRA_FAILURE is set but no backend-specific test logic is "
        "implemented. Add test logic above this line."
    )


# ---------------------------------------------------------------------------
# test_log_output_captured
#
# WHY: stdout from the step must be visible in run logs. Backends that redirect
# stdout to /dev/null, or that do not wire up mflog capture
# (export_mflog_env_vars + bash_capture_logs + BASH_SAVE_LOGS), produce
# empty log streams that make debugging impossible.
#
# Capability: Cap.LOG_STREAMING + Cap.MFLOG_CAPTURE (REQUIRED)
# ---------------------------------------------------------------------------


def test_log_output_captured(backend_config, flows_dir):
    """stdout printed inside a step must appear in the task log stream."""
    run = run_flow_with_backend(
        flow_path("log_flow.py", flows_dir),
        backend_config.decospec(),
    )

    assert run.successful, "LogFlow failed."

    log_token = run["log_step"].task.data.log_token
    assert log_token, "log_token artifact is empty — the step may not have run."

    loglines = list(run["log_step"].task.loglines("stdout"))
    log_text = "".join(line.line for line in loglines)

    assert log_token in log_text, (
        "Expected log token %r to appear in stdout loglines, but it was not found. "
        "Captured log text (first 500 chars): %r. "
        "The backend may not be wiring up mflog capture correctly: check "
        "export_mflog_env_vars, bash_capture_logs, and BASH_SAVE_LOGS." % (
            log_token, log_text[:500]
        )
    )


# ---------------------------------------------------------------------------
# test_conda_packages_available
#
# WHY: @pypi/@conda steps must resolve linux-64 packages regardless of the
# submitter OS. On macOS, the submitter resolves arm64/osx packages by
# default; backends must override the platform to linux-64 (or linux-aarch64)
# before submitting so the container receives the right packages.
#
# Note: @pypi is used here because @conda requires the conda binary to be
# installed on the submitter machine. @pypi is more universally available
# and exercises the same code path for platform resolution.
#
# Capability: Cap.CONDA (REQUIRED)
# ---------------------------------------------------------------------------


def test_conda_packages_available(backend_config, flows_dir):
    """
    @pypi steps must resolve linux packages regardless of the submitter OS.

    Verifies the exact version string, not just that the step succeeded, because
    a container with the system requests pre-installed could succeed silently
    while ignoring the pinned version entirely.
    """
    run = run_flow_with_backend(
        flow_path("conda_flow.py", flows_dir),
        backend_config.decospec(),
    )

    assert run.successful, (
        "CondaFlow failed. Check that the backend resolves linux-64 packages "
        "when the submitter is on a different OS."
    )
    requests_version = run["use_conda"].task.data.requests_version
    assert requests_version == "2.31.0", (
        "Expected requests==2.31.0, got %r. "
        "The backend may not be pinning the package version correctly, or may be "
        "falling back to a system-installed requests." % requests_version
    )


# ---------------------------------------------------------------------------
# test_metadata_readable_via_client
#
# WHY: Metadata written inside the container (task start/end times, task
# pathspec, tags) must reach the metadata service before the container exits.
# Backends that forget to call _replay_task_metadata_to_service (or its
# equivalent) produce runs that appear to be running forever from the client's
# perspective.
#
# Capability: Cap.METADATA_SYNC (REQUIRED)
# ---------------------------------------------------------------------------


def test_metadata_readable_via_client(backend_config, flows_dir):
    """Metadata written inside the container must be visible via the client API."""
    from metaflow import Run

    run = run_flow_with_backend(
        flow_path("artifact_flow.py", flows_dir),
        backend_config.decospec(),
    )

    assert run.successful, "ArtifactFlow failed."

    # Re-fetch via the client API to verify metadata reached the service.
    refreshed = Run(run.pathspec)
    assert refreshed.successful, (
        "Run.successful is False when fetched via Run(pathspec). "
        "Metadata may not have been synced to the service."
    )
    # metaflow always adds a "metaflow_version:X.Y.Z" system tag;
    # its presence confirms the metadata service received the run's metadata.
    version_tags = [t for t in refreshed.tags if t.startswith("metaflow_version:")]
    assert version_tags, (
        "No 'metaflow_version:*' system tag found after re-fetching via Run(pathspec). "
        "This tag is written by the metadata service on every run. "
        "Its absence suggests metadata was not synced to the service before "
        "the container exited."
    )


# ---------------------------------------------------------------------------
# test_resources_merge_with_decorator
#
# WHY: @resources values must not be silently ignored when combined with the
# backend decorator. Some backends overwrite the resource request with their
# own defaults instead of applying max() per field as the spec requires.
# At minimum, the combination must not crash.
#
# Full enforcement testing requires inspecting the actual job submission
# payload — add backend-specific assertions here.
#
# Capability: Cap.RESOURCES_MERGE (REQUIRED)
# ---------------------------------------------------------------------------


def test_resources_merge_with_decorator(backend_config, flows_dir):
    """
    @resources combined with the backend decorator must not crash.

    Full enforcement testing requires inspecting the actual job submission
    payload — add backend-specific assertions here.
    """
    run = run_flow_with_backend(
        flow_path("resources_flow.py", flows_dir),
        backend_config.decospec(),
    )

    assert run.successful, (
        "ResourcesFlow failed when @resources(cpu=1, memory=1024) is combined "
        "with the backend decorator. The backend may not be merging resource "
        "requests correctly."
    )
    # Full enforcement: add backend-specific assertions here to verify the
    # job was submitted with cpu=max(decorator_cpu, resources_cpu) etc.


# ---------------------------------------------------------------------------
# test_foreach_unique_task_ids
#
# WHY: Parallel foreach tasks must write to unique task IDs. If all tasks
# share the same task ID, later writes overwrite earlier ones and the join
# step sees only one value instead of all three.
#
# Capability: Cap.DATASTORE_ACCESS (REQUIRED — foreach parallel)
# ---------------------------------------------------------------------------


def test_foreach_unique_task_ids(backend_config, flows_dir):
    """Foreach tasks must write to distinct task IDs in the datastore."""
    run = run_flow_with_backend(
        flow_path("foreach_flow.py", flows_dir),
        backend_config.decospec(),
    )

    assert run.successful, "ForeachFlow failed."

    tasks = list(run["process_item"].tasks())
    assert len(tasks) == 3, (
        "Expected 3 process_item tasks (one per foreach item), got %d. "
        "Foreach fan-out may not be working." % len(tasks)
    )

    task_ids = [t.id for t in tasks]
    assert len(set(task_ids)) == 3, (
        "Foreach tasks do not have unique task IDs: %s. "
        "All tasks writing to the same ID means only the last write survives." % task_ids
    )

    values = {t.data.value for t in tasks}
    assert values == {1, 2, 3}, (
        "Expected foreach values {1, 2, 3}, got %r. "
        "Task ID collisions may have caused some writes to be lost." % values
    )


# ===========================================================================
# OPTIONAL tests
# ===========================================================================


# ---------------------------------------------------------------------------
# test_gpu_resource_request
#
# WHY: GPU resource requests must reach the scheduler and result in a container
# with a CUDA-capable device. Backends that ignore the gpu= parameter produce
# containers without GPUs that fail torch.cuda.is_available().
#
# Capability: Cap.GPU (OPTIONAL)
# ---------------------------------------------------------------------------


def test_gpu_resource_request(backend_config, flows_dir):
    """GPU containers must have a CUDA device available."""
    _require_cap(backend_config, Cap.GPU)

    run = run_flow_with_backend(
        flow_path("gpu_flow.py", flows_dir),
        backend_config.decospec(),
    )

    assert run.successful, "GpuFlow failed."
    gpu_available = run["check_gpu"].task.data.gpu_available
    assert gpu_available is True, (
        "torch.cuda.is_available() returned False inside the container. "
        "The backend may not be requesting a GPU or the container image "
        "may not have CUDA drivers installed."
    )


# ---------------------------------------------------------------------------
# test_memory_limit
#
# WHY: Memory limits specified via @resources(memory=...) or the backend
# decorator's own memory parameter must be honored by the job submission.
# Testing enforcement automatically requires causing an OOM kill and
# verifying the exit code, which is environment-dependent.
#
# Capability: Cap.CPU_MEMORY (OPTIONAL)
# ---------------------------------------------------------------------------


def test_memory_limit(backend_config, flows_dir):
    """Memory limits must be passed to the scheduler."""
    _require_cap(backend_config, Cap.CPU_MEMORY)

    pytest.skip(
        "CPU_MEMORY enforcement requires inspecting the job submission payload "
        "or deliberately triggering an OOM kill and verifying the container exits "
        "with the correct code. Add backend-specific assertions here."
    )


# ---------------------------------------------------------------------------
# test_timeout_kills_job
#
# WHY: A backend-level timeout must kill the remote job when exceeded. Backends
# that do not wire the timeout parameter to the scheduler let runaway steps
# accumulate indefinitely, wasting compute and blocking retries.
#
# Capability: Cap.TIMEOUT (OPTIONAL)
# ---------------------------------------------------------------------------


def test_timeout_kills_job(backend_config, flows_dir):
    """A step that exceeds its timeout must be killed by the backend."""
    _require_cap(backend_config, Cap.TIMEOUT)

    import tempfile
    import textwrap

    # Write a temporary flow that sleeps longer than any reasonable timeout.
    # The backend decorator is expected to kill the job before it finishes.
    timeout_flow_src = textwrap.dedent(
        """
        from metaflow import FlowSpec, step
        import time

        class TimeoutFlow(FlowSpec):
            @step
            def start(self):
                self.next(self.sleepy_step)

            @step
            def sleepy_step(self):
                time.sleep(1000)
                self.next(self.end)

            @step
            def end(self):
                pass
        """
    )

    with tempfile.NamedTemporaryFile(
        suffix="_timeout_flow.py", mode="w", delete=False
    ) as f:
        f.write(timeout_flow_src)
        tmp_path = f.name

    try:
        # Pass a short timeout (10 s) via run_kwargs so the backend enforces it.
        # run_flow_with_backend must propagate run_kwargs to Runner(...).run(**run_kwargs).
        run = run_flow_with_backend(
            tmp_path,
            backend_config.decospec(),
            run_kwargs={"timeout": 10},
        )
        assert not run.successful, (
            "Expected the run to fail due to timeout, but it succeeded. "
            "The backend may not be enforcing the timeout parameter."
        )
    finally:
        os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# test_infra_retry_loop
#
# WHY: METAFLOW_<BACKEND>_MAX_INFRA_RETRIES must cause transient infrastructure
# failures to be retried transparently, without counting against the user's
# @retry budget. Testing this requires a way to inject transient infra
# failures, which is backend-specific.
#
# Capability: Cap.INFRA_RETRY (OPTIONAL)
# ---------------------------------------------------------------------------


def test_infra_retry_loop(backend_config, flows_dir):
    """Transient infrastructure failures must be retried within the backend."""
    _require_cap(backend_config, Cap.INFRA_RETRY)

    pytest.skip(
        "INFRA_RETRY must be tested manually: configure MAX_INFRA_RETRIES, "
        "inject a transient infrastructure failure (e.g. spot preemption), "
        "and verify the step succeeds without consuming the @retry budget. "
        "Add backend-specific test logic here."
    )


# ---------------------------------------------------------------------------
# test_multinode_worker_task_ids
#
# WHY: Distributed training requires worker task IDs to be derived as
# {task_id}-worker-{i} so each worker writes to a unique path in the
# datastore. If all workers share the task_id, they collide.
#
# Capability: Cap.MULTINODE (OPTIONAL)
# ---------------------------------------------------------------------------


def test_multinode_worker_task_ids(backend_config, flows_dir):
    """Multinode worker tasks must use derived task IDs to avoid datastore collisions."""
    _require_cap(backend_config, Cap.MULTINODE)

    pytest.skip(
        "MULTINODE must be tested manually: run a distributed training step with "
        "num_parallel > 1 and verify that each worker task has a unique task ID "
        "of the form {task_id}-worker-{i}. "
        "Add backend-specific test logic here."
    )
