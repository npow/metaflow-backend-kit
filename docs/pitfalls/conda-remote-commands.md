# Pitfall: conda remote command aliases not patched

## Symptom

`@conda` or `@pypi` steps fail with package resolution errors, or silently install
the wrong architecture (e.g. osx-arm64 packages in a Linux container) when the
flow is submitted from macOS.

## Root cause

Setting `supports_conda_environment = True` on your decorator tells Metaflow that
your backend supports conda. It does NOT automatically set the target platform for
package resolution. If the submitter is on macOS and you don't override the platform,
the conda resolver will try to fetch `osx-arm64` or `osx-64` packages — which won't
run in your Linux container.

Additionally, if `CONDA_REMOTE_COMMANDS` is not patched, the conda resolver may use
incorrect command aliases for cross-platform resolution.

## Broken pattern (phala, bacalhau)

```python
supports_conda_environment = True
# No target_platform. No CONDA_REMOTE_COMMANDS patch.
# Works on Linux submitters, silently broken on macOS submitters.
```

## Fixed pattern (modal, akash, sandbox)

```python
supports_conda_environment = True

def _default_target_platform(self):
    import platform
    arch = platform.machine().lower()
    if arch in ("aarch64", "arm64"):
        return "linux-aarch64"
    return "linux-64"

def step_init(self, flow, graph, step, decos, environment, flow_datastore, logger):
    self.target_platform = self._default_target_platform()
    self._ensure_conda_remote_command_aliases(environment)
```

## Notes

- Don't hardcode `"linux-64"`. Akash and sandbox detect arm64 automatically.
- `_ensure_conda_remote_command_aliases()` is provided by Metaflow's conda
  environment object — call it in `step_init` after setting `target_platform`.
- If your backend only supports x86_64 Linux, hardcoding `"linux-64"` is fine,
  but you should document that ARM hosts are unsupported.
