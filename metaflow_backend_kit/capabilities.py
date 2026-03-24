from enum import Enum


class Cap(Enum):
    # --- REQUIRED ---

    # All METAFLOW_* env vars reach the remote container
    ENV_PROPAGATION = "env_propagation"

    # Code package uploaded to a URL accessible from the remote container
    # (not a local filesystem path)
    CODE_PACKAGE = "code_package"

    # Backend's native attempt counter converted to Metaflow's 0-indexed retry_count.
    # Most backends are 1-indexed; must use max(0, counter - 1).
    RETRY_COUNT = "retry_count"

    # Container can read/write to the configured datastore after the step runs.
    # Datastore credentials must be explicitly forwarded (not assumed ambient).
    DATASTORE_ACCESS = "datastore_access"

    # Infrastructure failures use METAFLOW_EXIT_DISALLOW_RETRY; user code failures
    # return the real exit code so Metaflow's @retry logic can handle them.
    INFRA_EXIT_CODE = "infra_exit_code"

    # stdout/stderr streamed in real time (not just available post-mortem).
    LOG_STREAMING = "log_streaming"

    # export_mflog_env_vars + bash_capture_logs + BASH_SAVE_LOGS wired up correctly.
    MFLOG_CAPTURE = "mflog_capture"

    # --environment conda forwarded to step command; CONDA_REMOTE_COMMANDS patched
    # to resolve linux-64 (or linux-aarch64) packages regardless of submitter OS.
    CONDA = "conda"

    # Local metadata replayed to service after task completes
    # (_replay_task_metadata_to_service or equivalent).
    METADATA_SYNC = "metadata_sync"

    # Decorator params merged with @resources using max() per field.
    RESOURCES_MERGE = "resources_merge"

    # --- OPTIONAL ---

    # GPU resource requests honored by the backend.
    GPU = "gpu"

    # CPU and memory limits enforced by the backend.
    CPU_MEMORY = "cpu_memory"

    # Backend-level timeout kills the remote job (not just decorator-level).
    TIMEOUT = "timeout"

    # METAFLOW_<BACKEND>_MAX_INFRA_RETRIES loop retries transient infra failures
    # without counting against the user's @retry budget.
    INFRA_RETRY = "infra_retry"

    # Azure Blob and GCS datastore support beyond S3.
    MULTI_DATASTORE = "multi_datastore"

    # Distributed training: worker task IDs derived as {task_id}-worker-{i}.
    MULTINODE = "multinode"


REQUIRED = {
    Cap.ENV_PROPAGATION,
    Cap.CODE_PACKAGE,
    Cap.RETRY_COUNT,
    Cap.DATASTORE_ACCESS,
    Cap.INFRA_EXIT_CODE,
    Cap.LOG_STREAMING,
    Cap.MFLOG_CAPTURE,
    Cap.CONDA,
    Cap.METADATA_SYNC,
    Cap.RESOURCES_MERGE,
}

OPTIONAL = {
    Cap.GPU,
    Cap.CPU_MEMORY,
    Cap.TIMEOUT,
    Cap.INFRA_RETRY,
    Cap.MULTI_DATASTORE,
    Cap.MULTINODE,
}
