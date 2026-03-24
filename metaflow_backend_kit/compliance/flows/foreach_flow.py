from metaflow import FlowSpec, step


class ForeachFlow(FlowSpec):
    @step
    def start(self):
        self.items = [1, 2, 3]
        self.next(self.process_item, foreach="items")

    @step
    def process_item(self):
        self.value = self.input
        self.next(self.join)

    @step
    def join(self, inputs):
        self.values = [inp.value for inp in inputs]
        self.next(self.end)

    @step
    def end(self):
        pass
