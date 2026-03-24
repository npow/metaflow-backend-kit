from metaflow import FlowSpec, step, retry, current


class RetryFlow(FlowSpec):
    @step
    def start(self):
        self.next(self.store_retry_count)

    @retry(times=1)
    @step
    def store_retry_count(self):
        # First attempt: record retry_count (must be 0) then fail so
        # the @retry decorator exercises the retry path.
        # Second attempt: record retry_count (must be 1) and continue.
        if current.retry_count == 0:
            self.first_attempt_retry_count = current.retry_count
            raise Exception("Deliberate failure to exercise @retry on store_retry_count")
        self.second_attempt_retry_count = current.retry_count
        self.next(self.flaky_step)

    @retry(times=2)
    @step
    def flaky_step(self):
        if current.retry_count == 0:
            raise Exception("Deliberate failure on attempt 0")
        self.succeeded_on_attempt = current.retry_count
        self.next(self.end)

    @step
    def end(self):
        pass
