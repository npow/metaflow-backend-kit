# Pitfall: code package path is local-only

## Symptom

Step fails immediately with "file not found" or "no such file or directory" when the
package extraction command runs inside the remote container.

## Root cause

`_save_package_once()` saves the code package to the configured datastore and returns
a remote URL (S3, GCS, Azure Blob). However, it also writes a local temp file during
the upload process. If you accidentally capture the local temp path instead of the
datastore URL, the remote container tries to access a path that only exists on the
submitting machine.

## Broken pattern

```python
class MyBackendDecorator(StepDecorator):
    package_local_path = None  # ← captures the local tmp file

    def runtime_task_created(self, ...):
        self.package_local_path = self._save_package_once(environment, flow_datastore, ...)
        # BUG: package_local_path is a local /tmp/... path
```

## Fixed pattern

```python
class MyBackendDecorator(StepDecorator):
    package_url = None
    package_sha = None
    package_metadata = None

    @classmethod
    def _save_package_once(cls, environment, flow_datastore, ...):
        if cls.package_url is None:
            pkg = MetaflowCodePackage(environment, flow_datastore)
            cls.package_url = pkg.package_url()
            cls.package_sha = pkg.package_sha()
            cls.package_metadata = pkg.package_metadata()
        return cls.package_url, cls.package_sha, cls.package_metadata
```

Then pass `package_url` (the remote URL) to the container's bootstrap command — never
the local temp path.

## Notes

- The class-level pattern (not instance-level) is intentional: all steps in the same
  flow run share one code package upload. Uploading once per step is wasteful and can
  cause race conditions in large foreach fan-outs.
- For backends that SSH into VMs (akash), you can SFTP the local tarball directly
  instead of downloading from the datastore. Keep the local path for that case, but
  only use it for SFTP — not for remote download commands.
