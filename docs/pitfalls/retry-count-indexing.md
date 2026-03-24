# Pitfall: retry counter indexing mismatch

## Symptom

`current.retry_count` inside a step always reads 1 on the first attempt instead of 0.
`@catch` skips catching exceptions on the first attempt. Retry budgets are consumed
one attempt earlier than expected.

## Root cause

Backend platforms (Modal, Akash, Bacalhau, etc.) typically start their attempt
counters at 1. Metaflow expects 0-indexed retry_count (first execution = 0).
If you pass the backend counter directly, every execution looks like a retry.

## Broken pattern

```python
def runtime_step_cli(self, cli_args, retry_count, max_user_code_retries, ubf_context):
    # backend_attempt is 1 on the first execution
    backend_attempt = self._get_backend_attempt_number()
    return cli_args.step(
        ...,
        retry_count=backend_attempt,  # BUG: off by one
    )
```

## Fixed pattern

```python
    backend_attempt = self._get_backend_attempt_number()  # 1-indexed
    mf_retry_count = max(0, backend_attempt - 1)          # convert to 0-indexed
    return cli_args.step(
        ...,
        retry_count=mf_retry_count,
    )
```

## Notes

- This is identical to the orchestrator pitfall (#27 in metaflow-orchestrator-kit).
- Some backends may be 0-indexed already — check your platform's documentation.
- If the backend doesn't expose a native attempt counter, derive from Metaflow's
  own retry_count parameter passed to `runtime_step_cli`.
