"""
Centralized, externalized prompt text. Every prompt an LLM-backed provider
or agent sends lives here, never inline in a provider/service/agent module -
so prompt wording can be reviewed/changed without touching business logic.
"""

from __future__ import annotations
