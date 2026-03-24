from metaflow import FlowSpec, step


class LogFlow(FlowSpec):
    @step
    def start(self):
        self.next(self.log_step)

    @step
    def log_step(self):
        import uuid

        self.log_token = str(uuid.uuid4())
        print(self.log_token)
        self.next(self.end)

    @step
    def end(self):
        pass
