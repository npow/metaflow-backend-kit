# metaflow-backend-kit

[![CI](https://github.com/npow/metaflow-backend-kit/actions/workflows/ci.yml/badge.svg)](https://github.com/npow/metaflow-backend-kit/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/metaflow-backend-kit)](https://pypi.org/project/metaflow-backend-kit/)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Docs](https://img.shields.io/badge/docs-mintlify-18a34a?style=flat-square)](https://mintlify.com/npow/metaflow-backend-kit)

**Build a Metaflow compute backend in hours, not weeks.**

Metaflow lets you run steps on any compute backend — AWS Batch, Kubernetes, Modal, your own cluster. This kit gives you three tools to build your own backend:

1. **Scaffold** — generates all the files you need to get started
2. **Validate** — catches common mistakes before you run anything
3. **Compliance tests** — proves your backend actually works end-to-end

---

## Quickstart

```bash
pip install metaflow-backend-kit

# 1. Generate a skeleton for your backend
metaflow-backend-scaffold mybackend

# 2. Fill in the TODOs (job submission, log streaming, status polling)
#    Edit: mybackend/mybackend_executor.py

# 3. Check for common mistakes
metaflow-backend-validate mybackend/

# 4. Run end-to-end compliance tests
metaflow-backend-test --backend mybackend
```

---

## What gets generated

```
mybackend/
  mybackend_decorator.py   # The @mybackend step decorator
  mybackend_executor.py    # Submit jobs, stream logs, wait for results
  mybackend_cli.py         # CLI entry point Metaflow calls per-step
  mybackend_client.py      # Thin wrapper around your backend's API
  plugins/__init__.py      # Registers everything with Metaflow
  ux-tests-mybackend.yml   # GitHub Actions CI workflow
```

Open `mybackend_executor.py` and fill in three methods:

```python
def _submit_job(self) -> None:
    # TODO: submit self._cmd to your backend, save self._job_id

def _stream_logs(self) -> None:
    # TODO: tail logs from self._job_id in real time

def _wait(self) -> int:
    # TODO: poll until done, return exit code
```

That's the core. Everything else is wired up for you.

---

## Validate before you run

```bash
metaflow-backend-validate mybackend/
```

```
✓  extension registration exists
✓  SUPPORTED_CAPABILITIES declared
✓  retry_count not hardcoded
✓  METAFLOW_RUNTIME_ENVIRONMENT set
✓  METAFLOW_EXIT_DISALLOW_RETRY used
✓  auth env vars forwarded to container
✓  code package uploaded via datastore
⚠  metadata sync present
   No metadata sync found. Local metadata may not reach the service.
   → See docs/pitfalls/metadata-sync.md

Results: 15 passed, 1 warned
```

---

## Compliance tests

Once your backend submits real jobs:

```bash
# Basic run
metaflow-backend-test --backend mybackend

# With optional capabilities
metaflow-backend-test --backend mybackend --supported-caps GPU,TIMEOUT

# With a specific container image
metaflow-backend-test --backend mybackend --backend-image ubuntu:22.04
```

Each test covers one thing: env vars reach the container, artifacts persist, retry counts are correct, logs stream, metadata syncs. If a test fails, the message tells you exactly what broke and why.

---

## Pitfall guides

The most common mistakes each have a doc in [`docs/pitfalls/`](docs/pitfalls/):

| Pitfall | Doc |
|---------|-----|
| Backend uses 1-indexed attempt counters | `retry-count-indexing.md` |
| Credentials disappear inside the container | `credentials-import-time.md` |
| Task metadata lost after container exits | `metadata-sync.md` |
| Infra failures consume @retry budget | `infra-vs-step-exit-code.md` |
| Wrong packages resolved on macOS → Linux | `conda-remote-commands.md` |
| `@resources` values silently ignored | `resources-merge.md` |

---

## License

[Apache 2.0](LICENSE)
