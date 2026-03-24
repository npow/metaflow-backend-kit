# Pitfall: infrastructure failure treated as retryable step failure

## Symptom

A step that fails due to a provisioning error, bad credentials, or platform OOM
gets retried by Metaflow's `@retry` decorator, burning retry budget on failures
that will never succeed. Or the inverse: a real step failure (user code bug) is
treated as an infrastructure failure and not retried when it should be.

## Root cause

Metaflow uses the step's exit code to decide whether to retry. Exit code 0 = success,
non-zero = failure (retry if budget remains). `METAFLOW_EXIT_DISALLOW_RETRY` is a
special exit code that signals "do not retry this — it's permanent."

Backend implementations must correctly distinguish:
1. **Infrastructure failure** (provisioning error, auth failure, platform OOM, timeout
   by the backend) → `sys.exit(METAFLOW_EXIT_DISALLOW_RETRY)`
2. **Step failure** (user code raised an exception, `sys.exit(1)`) → return the real
   exit code so Metaflow's `@retry` can handle it

## Broken pattern

```python
try:
    exit_code = run_remote_job(cmd)
    sys.exit(exit_code)
except Exception as e:
    # BUG: catches everything including infra failures as retryable
    raise
```

## Fixed pattern

```python
from metaflow.exception import METAFLOW_EXIT_DISALLOW_RETRY

try:
    job = submit_job(cmd)
except ProvisioningError as e:
    # Infrastructure failure — don't retry
    logger("Provisioning failed: %s" % e, bad=True)
    sys.exit(METAFLOW_EXIT_DISALLOW_RETRY)

exit_code = job.wait()

if exit_code == 137:  # OOM killed by platform
    sys.exit(METAFLOW_EXIT_DISALLOW_RETRY)
elif exit_code == 124:  # timeout
    sys.exit(METAFLOW_EXIT_DISALLOW_RETRY)
else:
    # User code exit code — let Metaflow decide whether to retry
    sys.exit(exit_code)
```

## Notes

- Platform-specific exit codes (137 = OOM, 124 = timeout) vary. Document which
  codes your backend maps to `METAFLOW_EXIT_DISALLOW_RETRY`.
- If your backend raises exceptions for infra failures instead of returning exit
  codes, catch them specifically (not `except Exception`) before the wait loop.
- Modal sandbox: use `raise_on_termination=False` so preemption (137) and timeout
  (124) return as exit codes rather than exceptions, then map them explicitly.
