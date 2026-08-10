"""PipelineStage: one step in the ingest/publish pipeline."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pipeline.context import PipelineContext


class PipelineStage(ABC):
    name: str

    @abstractmethod
    def run(self, ctx: PipelineContext) -> PipelineContext:
        ...
