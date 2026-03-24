from metaflow import FlowSpec, step


class GpuFlow(FlowSpec):
    @step
    def start(self):
        self.next(self.check_gpu)

    @step
    def check_gpu(self):
        try:
            import torch

            self.gpu_available = torch.cuda.is_available()
        except ImportError:
            self.gpu_available = False
        self.next(self.end)

    @step
    def end(self):
        pass
