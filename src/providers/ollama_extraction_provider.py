"""
OllamaExtractionProvider: real entity + relationship extraction via a local
Ollama-served chat model (Qwen3 14B by default). Chunks are grouped into
batches (batch_size, default 8) and each batch is sent as one combined
/api/chat call returning both entities and relationships per chunk_id as
JSON (format: "json") - matching the requested Chunk -> LocalExtractionProvider
-> entities + relationships flow while avoiding a per-chunk model round-trip.
Batching matters here because most chunks in this corpus are far smaller
than the model's context window, so one round-trip per chunk pays fixed
prompt/inference overhead for very little content each time. "think" is
explicitly disabled - this is a structured extraction task, not one that
benefits from the model's hidden chain-of-thought, and skipping it is a
major latency win on CPU-only inference.

The model classifies into the *existing* ontology's entity_types/
relationship_types (passed into the prompt as the allowed vocabulary) - any
entity/relationship referencing an out-of-vocabulary type, or a relationship
whose source/target name doesn't match an entity actually extracted from
that chunk, is dropped defensively (same spirit as the rule-based extractor
only ever emitting known ontology types). Malformed/unparseable model output
is treated as zero results for the affected chunk(s), not a hard pipeline
failure.

Raw per-chunk responses are cached on the instance keyed by chunk_id, so
extract_relationships() reuses the extract_entities() pass instead of
re-invoking the model, except for a chunk that was never seen by
extract_entities() (e.g. a relationship-only re-run), which falls back to a
single-chunk batch-of-one call.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from config.app_config import AppConfig
from extraction.id_utils import build_entity_id
from ontology.rdf.graph_loader import load_ontology_graph
from ontology.rdf.hierarchy import class_labels_and_keywords
from prompts.entity_relationship_extraction import SYSTEM_PROMPT, build_extraction_prompt
from providers.extraction_provider import ExtractionProvider

logger = logging.getLogger("kg_local")

_EMPTY_RESULT = {"entities": [], "relationships": []}
_NO_FIT_TYPE = "NO_FIT"
_NO_FIT_EVIDENCE_LENGTH = 200


def _coerce_confidence(value) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.5
    return min(1.0, max(0.0, score))


class OllamaExtractionProvider(ExtractionProvider):
    def __init__(self, config: AppConfig) -> None:
        options = config.extraction.options.get("ollama", {})
        self.base_url = options.get("base_url", "http://localhost:11434")
        self.model = options.get("model", "qwen3:14b")
        self.request_timeout_seconds = float(options.get("request_timeout_seconds", 120))
        self.batch_size = int(options.get("batch_size", 8))
        self._cache: dict[str, dict] = {}
        self._class_proposals: dict[str, dict] = {}

        rdf_graph = load_ontology_graph(config)
        self._rdf_entity_types = class_labels_and_keywords(rdf_graph) if rdf_graph is not None else {}

    def _extended_ontology(self, ontology: dict) -> dict:
        """Unions the RDF-derived class vocabulary (core classes plus every
        configured domain module, e.g. change_of_address.ttl) with
        ontology.yaml's own entity_types, so a new domain's OWL classes
        reach the LLM-fallback's prompt and type-validation without
        duplicating entries in the shared YAML file. No-op when no
        turtle_modules are configured."""
        if not self._rdf_entity_types:
            return ontology
        entity_types = dict(ontology.get("entity_types") or {})
        for class_name, keywords in self._rdf_entity_types.items():
            entity_types.setdefault(class_name, {"keywords": keywords})
        return {**ontology, "entity_types": entity_types}

    def _call_model_batch(self, chunks: list[dict], ontology: dict) -> dict[str, dict]:
        empty_results = {chunk["chunk_id"]: dict(_EMPTY_RESULT) for chunk in chunks}

        payload = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": build_extraction_prompt(chunks, ontology)},
                ],
                "format": "json",
                "stream": False,
                "think": False,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/api/chat",
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.request_timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
            content = body["message"]["content"]
            parsed = json.loads(content)
        except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError, TypeError) as exc:
            logger.warning("OllamaExtractionProvider: model call failed or returned unparseable output: %s", exc)
            return empty_results

        results = dict(empty_results)
        for raw_chunk in parsed.get("chunks") or []:
            chunk_id = raw_chunk.get("chunk_id")
            if chunk_id not in results:
                continue
            results[chunk_id] = {
                "entities": raw_chunk.get("entities") or [],
                "relationships": raw_chunk.get("relationships") or [],
            }
        return results

    def _invoke_batch(self, chunks: list[dict], ontology: dict) -> None:
        uncached = [chunk for chunk in chunks if chunk["chunk_id"] not in self._cache]
        for start in range(0, len(uncached), self.batch_size):
            batch = uncached[start : start + self.batch_size]
            self._cache.update(self._call_model_batch(batch, ontology))

    def _invoke_chunk(self, chunk: dict, ontology: dict) -> dict:
        self._invoke_batch([chunk], ontology)
        return self._cache[chunk["chunk_id"]]

    def extract_entities(self, chunks: list[dict], ontology: dict) -> tuple[list[dict], list[dict]]:
        ontology = self._extended_ontology(ontology)
        self._invoke_batch(chunks, ontology)
        allowed_types = set((ontology.get("entity_types") or {}).keys())

        entities_by_key: dict[tuple[str, str], dict] = {}
        mentions: list[dict] = []
        mention_keys: set[tuple[str, str]] = set()

        for chunk in chunks:
            raw = self._invoke_chunk(chunk, ontology)
            for raw_entity in raw["entities"]:
                name = str(raw_entity.get("name") or "").strip()
                entity_type = raw_entity.get("type")
                if not name:
                    continue
                if entity_type == _NO_FIT_TYPE:
                    self._collect_no_fit(raw_entity, name, chunk, allowed_types)
                    continue
                if entity_type not in allowed_types:
                    continue

                key = (name.lower(), entity_type)
                if key not in entities_by_key:
                    entities_by_key[key] = {
                        "id": build_entity_id(entity_type, name),
                        "name": name,
                        "type": entity_type,
                        "source_chunk": chunk["chunk_id"],
                        "confidence_score": _coerce_confidence(raw_entity.get("confidence_score")),
                    }

                entity_id = entities_by_key[key]["id"]
                mention_key = (chunk["chunk_id"], entity_id)
                if mention_key not in mention_keys:
                    mention_keys.add(mention_key)
                    mentions.append({"chunk_id": chunk["chunk_id"], "entity_id": entity_id})

        return list(entities_by_key.values()), mentions

    def _collect_no_fit(self, raw_entity: dict, name: str, chunk: dict, allowed_types: set[str]) -> None:
        """Accumulates a NO_FIT-flagged entity into self._class_proposals,
        keyed by lowercased name so the same proposed concept reappearing
        across chunks/batches merges into one row instead of duplicating -
        drained (and cleared) by get_class_proposals()."""
        suggested_parent = raw_entity.get("suggested_parent")
        if suggested_parent not in allowed_types:
            if suggested_parent is not None:
                logger.debug(
                    "OllamaExtractionProvider: NO_FIT suggested_parent %r for %r is not an "
                    "allowed type, clearing it",
                    suggested_parent,
                    name,
                )
            suggested_parent = None

        confidence = _coerce_confidence(raw_entity.get("confidence_score"))
        snippet = chunk["content"].strip().replace("\n", " ")[:_NO_FIT_EVIDENCE_LENGTH]

        key = name.lower()
        existing = self._class_proposals.get(key)
        if existing is None:
            self._class_proposals[key] = {
                "proposed_name": name,
                "suggested_parent": suggested_parent,
                "evidence": snippet,
                "source_chunks": [chunk["chunk_id"]],
                "confidence": confidence,
            }
            return

        if suggested_parent and not existing["suggested_parent"]:
            existing["suggested_parent"] = suggested_parent
        if chunk["chunk_id"] not in existing["source_chunks"]:
            existing["source_chunks"].append(chunk["chunk_id"])
        existing["confidence"] = max(existing["confidence"], confidence)

    def get_class_proposals(self) -> list[dict]:
        proposals = list(self._class_proposals.values())
        self._class_proposals.clear()
        return proposals

    def extract_relationships(
        self, chunks: list[dict], entities: list[dict], mentions: list[dict], ontology: dict
    ) -> list[dict]:
        allowed_types = set((ontology.get("relationship_types") or {}).keys())
        entity_by_id = {e["id"]: e for e in entities}

        entities_per_chunk: dict[str, list[dict]] = {}
        for mention in mentions:
            entities_per_chunk.setdefault(mention["chunk_id"], []).append(entity_by_id[mention["entity_id"]])

        all_relationships: list[dict] = []
        seen_global: set[tuple[str, str, str]] = set()

        for chunk in chunks:
            raw = self._invoke_chunk(chunk, ontology)
            name_to_id = {e["name"].lower(): e["id"] for e in entities_per_chunk.get(chunk["chunk_id"], [])}

            for raw_rel in raw["relationships"]:
                rel_type = raw_rel.get("relationship")
                if rel_type not in allowed_types:
                    continue

                source_id = name_to_id.get(str(raw_rel.get("source") or "").strip().lower())
                target_id = name_to_id.get(str(raw_rel.get("target") or "").strip().lower())
                if not source_id or not target_id or source_id == target_id:
                    continue

                key = (source_id, rel_type, target_id)
                if key in seen_global:
                    continue
                seen_global.add(key)

                all_relationships.append(
                    {
                        "source": source_id,
                        "relationship": rel_type,
                        "target": target_id,
                        "source_chunk": chunk["chunk_id"],
                        "confidence_score": _coerce_confidence(raw_rel.get("confidence_score")),
                    }
                )

        return all_relationships
