from metaflow import FlowSpec, step


class ArtifactFlow(FlowSpec):
    @step
    def start(self):
        self.next(self.write_artifact)

    @step
    def write_artifact(self):
        self.result = 42
        self.message = "hello from backend"
        self.next(self.end)

    @step
    def end(self):
        assert self.result == 42
