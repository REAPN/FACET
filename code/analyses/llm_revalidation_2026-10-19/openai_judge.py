#!/usr/bin/env python3
import json
from typing import Any, Dict, Tuple

_client = None


def call_openai_with_usage(model: str, system: str, user: str, seed: int,
                           schema: Dict[str, Any]) -> Tuple[Dict[str, Any], Tuple[int, int, str]]:
    global _client
    from openai import OpenAI
    if _client is None:
        _client = OpenAI()
    resp = _client.chat.completions.create(
        model=model, temperature=0, seed=seed,
        messages=[{"role": "developer", "content": system}, {"role": "user", "content": user}],
        response_format={"type": "json_schema", "json_schema": schema},
    )
    obj = json.loads(resp.choices[0].message.content)
    u = getattr(resp, "usage", None)
    tin = int(getattr(u, "prompt_tokens", 0) or 0)
    tout = int(getattr(u, "completion_tokens", 0) or 0)
    return obj, (tin, tout, getattr(resp, "model", None))
