#!/usr/bin/env python3
import json
from typing import Any, Dict, Optional


def _bundle_pydantic():
    from enum import Enum
    from typing import List
    from pydantic import BaseModel

    class RerankAction(str, Enum):
        promote = "promote"; keep = "keep"; demote = "demote"; abstain = "abstain"

    class EvidenceScope(str, Enum):
        organism_behavior = "organism_behavior"
        organism_sensory = "organism_sensory"
        developmental_behavior = "developmental_behavior"
        cellular_or_circuit_only = "cellular_or_circuit_only"
        unclear = "unclear"

    class BehavioralAnalogType(str, Enum):
        direct_analog = "direct_analog"; close_support = "close_support"
        weak_support = "weak_support"; mechanistic_only = "mechanistic_only"; mismatch = "mismatch"

    class Item(BaseModel):
        candidate_index: int
        rerank_action: RerankAction
        comparable_observable: bool
        evidence_scope: EvidenceScope
        behavioral_analog_type: BehavioralAnalogType
        strict_eligible: bool
        broad_eligible: bool
        reason: str

    class Bundle(BaseModel):
        target_id: str
        selected_candidates: List[Item]

    return Bundle


def call_openai(model: str, system: str, user: str, seed: int, schema: Dict[str, Any]) -> Dict[str, Any]:
    from openai import OpenAI
    client = OpenAI()
    resp = client.chat.completions.create(
        model=model, temperature=0, seed=seed,
        messages=[{"role": "developer", "content": system}, {"role": "user", "content": user}],
        response_format={"type": "json_schema", "json_schema": schema},
    )
    return json.loads(resp.choices[0].message.content)


def call_gemini(model: str, system: str, user: str, seed: int) -> Dict[str, Any]:
    from google import genai
    from google.genai import types
    Bundle = _bundle_pydantic()
    client = genai.Client()
    resp = client.models.generate_content(
        model=model, contents=user,
        config=types.GenerateContentConfig(
            system_instruction=system, temperature=0.0, seed=seed,
            response_mime_type="application/json", response_schema=Bundle,
        ),
    )
    return json.loads(resp.text)


def call_claude(model: str, system: str, user: str, schema: Dict[str, Any]) -> Dict[str, Any]:
    import anthropic
    client = anthropic.Anthropic()
    input_schema = schema.get("schema", schema)
    tool = {"name": "record_bundle",
            "description": "Record the rerank judgments for every listed candidate in the bundle.",
            "input_schema": input_schema}
    resp = client.messages.create(
        model=model, max_tokens=4096, system=system,
        messages=[{"role": "user", "content": user}],
        tools=[tool], tool_choice={"type": "tool", "name": "record_bundle"},
    )
    blk = next((b.input for b in resp.content if b.type == "tool_use" and b.name == "record_bundle"), None)
    if blk is None:
        raise RuntimeError("Claude returned no record_bundle tool_use block")
    return blk


def bundle_judgment(backend: str, model: str, system: str, user: str,
                    seed: int = 1, schema: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if backend == "openai":
        return call_openai(model, system, user, seed, schema)
    if backend == "gemini":
        return call_gemini(model, system, user, seed)
    if backend == "claude":
        return call_claude(model, system, user, schema)
    raise ValueError(f"unknown backend: {backend} (stub is handled in the driver)")
