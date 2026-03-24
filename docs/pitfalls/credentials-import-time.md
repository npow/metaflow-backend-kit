# Pitfall: auth credentials captured too late

## Symptom

The backend fails to authenticate even though the correct credentials are in the
environment when the user runs the flow. Intermittent auth failures when mixing
decorators that mutate the environment.

## Root cause

By the time `step_init` or `runtime_step_cli` runs, other decorators (conda,
environment, custom) may have mutated `os.environ`. Credentials read at that point
may be stale or missing.

## Broken pattern

```python
class MyBackendDecorator(StepDecorator):
    def step_init(self, ...):
        # Too late — environment may already be mutated
        self.token_id = os.environ.get("MY_BACKEND_TOKEN_ID")
        self.token_secret = os.environ.get("MY_BACKEND_TOKEN_SECRET")
```

## Fixed pattern (modal)

```python
# Module level — captured immediately at import, before any decorator runs
_AUTH_VARS = ["MY_BACKEND_TOKEN_ID", "MY_BACKEND_TOKEN_SECRET", "MY_BACKEND_ENV"]
_INITIAL_AUTH_ENV = {k: os.environ.get(k) for k in _AUTH_VARS if os.environ.get(k)}


class MyBackendDecorator(StepDecorator):
    def runtime_step_cli(self, ...):
        # Forward the captured-at-import values, not current os.environ
        env.update(_INITIAL_AUTH_ENV)
```

## Notes

- This matters most when users have environment-mutating decorators (e.g.
  `@environment(vars={"MY_BACKEND_TOKEN_ID": "..."})`), which run before
  `step_init` but after module import.
- Capture all backend auth vars at module level, not inside any method.
