from metaflow import FlowSpec, step, pypi


class CondaFlow(FlowSpec):
    @step
    def start(self):
        self.next(self.use_conda)

    @pypi(packages={"requests": "2.31.0"})
    @step
    def use_conda(self):
        import requests

        self.requests_version = requests.__version__
        self.next(self.end)

    @step
    def end(self):
        pass
