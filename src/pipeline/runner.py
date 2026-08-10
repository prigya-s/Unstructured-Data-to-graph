"""
PipelineRunner: ordered list of stages, run_all()/run_stage(name) - mirrors
a Databricks multi-task Workflow, where each stage is a task and a
Databricks Workflow's per-task entry points would call run_stage(name, ctx)
individually.
"""

from __future__ import annotations

from .context import PipelineContext
from .stages.base import PipelineStage


class PipelineRunner:
    def __init__(self, stages: list[PipelineStage]) -> None:
        self._order = [stage.name for stage in stages]
        self._stages = {stage.name: stage for stage in stages}

    def run_all(self, ctx: PipelineContext, through: str | None = None) -> PipelineContext:
        for name in self._order:
            ctx = self._stages[name].run(ctx)
            if name == through:
                break
        return ctx

    def run_stage(self, name: str, ctx: PipelineContext) -> PipelineContext:
        return self._stages[name].run(ctx)
