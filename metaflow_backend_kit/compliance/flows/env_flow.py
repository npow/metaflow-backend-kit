from metaflow import FlowSpec, step
import os


class EnvFlow(FlowSpec):
    @step
    def start(self):
        self.next(self.read_env)

    @step
    def read_env(self):
        self.metaflow_user = os.environ.get("METAFLOW_USER", "")
        self.next(self.end)

    @step
    def end(self):
        pass
