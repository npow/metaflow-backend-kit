# Pitfall: @resources decorator values silently ignored

## Symptom

A step decorated with both `@mybackend(cpu=2)` and `@resources(cpu=8)` runs with
only 2 CPUs. The user's explicit `@resources` request is ignored.

## Root cause

Metaflow has a canonical `@resources` decorator that users apply to set CPU, memory,
and GPU independently of the compute backend. Backend decorators are expected to
merge their own defaults with `@resources` values, taking the max of each field.
Most new backend implementations forget this entirely.

## Broken pattern

```python
class MyBackendDecorator(StepDecorator):
    defaults = {"cpu": 1, "memory": 4096, "gpu": 0}

    def step_init(self, flow, graph, step, decos, ...):
        # BUG: ignores @resources entirely
        self.cpu = self.attributes["cpu"]
        self.memory = self.attributes["memory"]
```

## Fixed pattern (bacalhau)

```python
    def step_init(self, flow, graph, step, decos, ...):
        # Find the @resources decorator if present
        resources_deco = next(
            (d for d in decos if d.name == "resources"), None
        )
        if resources_deco:
            for field in ("cpu", "memory", "gpu"):
                my_val = self.attributes.get(field) or 0
                res_val = resources_deco.attributes.get(field) or 0
                self.attributes[field] = max(my_val, res_val)
```

## Notes

- Use `max()` per field, not a wholesale override. A user might set `@resources(gpu=1)`
  while the backend default is `gpu=0` — taking the max gives them the GPU.
- `@resources` values are authoritative for users who want backend-agnostic resource
  declarations. Ignoring them breaks portability across backends.
- Field names match the `@resources` decorator: `cpu`, `memory`, `gpu`, `disk`.
