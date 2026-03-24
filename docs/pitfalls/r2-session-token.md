# Pitfall: AWS session token breaks Cloudflare R2

## Symptom

Steps fail with `InvalidAccessKeyId` or similar S3 auth errors when the user's
datastore is configured to use a Cloudflare R2 endpoint. Works fine with real AWS S3.

## Root cause

Cloudflare R2 uses an S3-compatible API but does not support temporary session tokens
(`AWS_SESSION_TOKEN` / `x-amz-security-token`). If you forward all AWS credential
env vars including `AWS_SESSION_TOKEN`, R2 rejects the request even when the
access key and secret are valid.

## Fixed pattern (sandbox)

```python
_FORWARDED_AWS_VARS = [
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_DEFAULT_REGION",
]

def _get_credential_env(self):
    env = {}
    s3_endpoint = os.environ.get("METAFLOW_S3_ENDPOINT_URL", "")
    for k in _FORWARDED_AWS_VARS:
        if k == "AWS_SESSION_TOKEN" and "cloudflarestorage.com" in s3_endpoint:
            continue  # R2 doesn't support session tokens
        v = os.environ.get(k)
        if v:
            env[k] = v
    return env
```

## Notes

- Also cap `METAFLOW_S3_WORKER_COUNT` to 8 for R2 endpoints — R2 has lower
  concurrency limits than AWS S3, and the default fan-out can trigger rate limiting.
- This pattern applies to any S3-compatible storage that doesn't support STS tokens
  (MinIO with static credentials, DigitalOcean Spaces, etc.).
