from metaflow import FlowSpec, step, resources


class ResourcesFlow(FlowSpec):
    @step
    def start(self):
        self.next(self.heavy_step)

    @resources(cpu=1, memory=1024)
    @step
    def heavy_step(self):
        self.done = True
        self.next(self.end)

    @step
    def end(self):
        pass
