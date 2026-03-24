# Pitfall: metadata written inside the container never reaches the service

## Symptom

`Run` objects retrieved via the Metaflow client API are missing metadata (tags,
attempt info, system metadata) for steps that ran on the backend. Metadata shows
up when running locally but not on the backend.

## Root cause

When `METAFLOW_DEFAULT_METADATA` is set to `service`, Metaflow inside the remote
container tries to POST metadata to the service URL. This works if the container has
network access to the service. But some backends (sandboxes, TEEs) may not have
service connectivity, so Metaflow falls back to writing metadata locally to the
datastore.

Local metadata written to the datastore must be explicitly replayed back to the
service after the task completes. If you don't do this, the metadata is silently
lost (no error, just missing data in the client API).

## Fixed pattern (modal, sandbox, akash)

In the CLI (`{name}_cli.py`), after the task completes:

```python
def _sync_metadata(flow_file, run_id, step_name, task_id, attempt):
    from metaflow.runner.utils import sync_local_metadata_to_service
    sync_local_metadata_to_service(
        "step_name",
        flow_datastore,
        run_id,
        step_name,
        task_id,
        attempt,
    )
```

In the decorator, switch to local metadata inside the container:

```python
def task_pre_step(self, step_name, task_datastore, metadata, ...):
    if metadata.TYPE == "service":
        # Can't reach service from inside container; write locally
        metadata.register_system_metadata(
            "attempt", str(self.attributes.get("retry_count", 0))
        )
```

## Notes

- GHA doesn't implement metadata sync — metadata from GHA steps is not available
  via the client API.
- The sync must happen after `task_finished`, not before — otherwise in-progress
  metadata (e.g. attempt start time) may not be written yet.
- This only matters when `METAFLOW_DEFAULT_METADATA=service`. If users run with
  local metadata, there's nothing to sync.
