"""
llm.py — local LLM client for LM Studio (or any OpenAI-compatible endpoint).

Per project preference, all "intense LLM work" runs against a LOCAL model served
by LM Studio, not a cloud API. LM Studio exposes an OpenAI-compatible server
(default http://localhost:1234/v1), so we just point the openai client at it.

Configuration (env vars, all optional):
    LLM_BASE_URL   default "http://localhost:1234/v1"
    LLM_API_KEY    default "lm-studio"   (LM Studio ignores the value)
    LLM_MODEL      default "google/gemma-4-26b-a4b"
    LLM_TEMP       default "0"

Nothing here is required by the core pipeline — collection, cleaning, dedupe,
and metrics are all deterministic and LLM-free. The LLM is opt-in (e.g.
`classify_event_type.py --llm`) and for later cognition/analysis work.

Quick check that your LM Studio server is up and the model is loaded:
    python llm.py --check
    python llm.py --prompt "Say hello in five words."
"""

from __future__ import annotations

import json
import os
from typing import Optional

DEFAULT_BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:1234/v1")
DEFAULT_API_KEY = os.environ.get("LLM_API_KEY", "lm-studio")
DEFAULT_MODEL = os.environ.get("LLM_MODEL", "google/gemma-4-26b-a4b")
DEFAULT_TEMP = float(os.environ.get("LLM_TEMP", "0"))


class LocalLLM:
    """Thin wrapper over an OpenAI-compatible chat endpoint (LM Studio)."""

    def __init__(self, base_url: str = DEFAULT_BASE_URL,
                 api_key: str = DEFAULT_API_KEY,
                 model: str = DEFAULT_MODEL,
                 temperature: float = DEFAULT_TEMP,
                 timeout: Optional[float] = None,
                 max_retries: int = 2):
        self.base_url = base_url
        self.model = model
        self.temperature = temperature
        try:
            from openai import OpenAI  # pip install openai
        except Exception as e:
            raise RuntimeError(
                "The 'openai' package is required for local LLM calls. "
                "Install with:  pip install openai"
            ) from e
        # A request timeout matters for batch jobs: without it, a server
        # restart or a hung generation blocks the whole run indefinitely
        # (observed). Caller picks a bound; the client raises on exceeding it.
        self._client = OpenAI(base_url=base_url, api_key=api_key,
                              timeout=timeout, max_retries=max_retries)

    def chat(self, prompt: str, system: Optional[str] = None,
             max_tokens: int = 512, temperature: Optional[float] = None) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature if temperature is None else temperature,
            max_tokens=max_tokens,
        )
        return (resp.choices[0].message.content or "").strip()

    def json_chat(self, prompt: str, system: Optional[str] = None,
                  max_tokens: int = 512, temperature: Optional[float] = None) -> dict:
        """
        Ask for JSON and parse it. Falls back to extracting the first {...} block
        if the model wraps the JSON in prose. `temperature` overrides the default
        (useful for a retry that perturbs a deterministic empty/garbled reply).
        """
        sys = (system or "") + "\nRespond with ONLY valid JSON. No prose, no code fences."
        raw = self.chat(prompt, system=sys.strip(), max_tokens=max_tokens,
                        temperature=temperature)
        raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            return json.loads(raw)
        except Exception:
            start, end = raw.find("{"), raw.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(raw[start:end + 1])
                except Exception:
                    pass
        return {}

    def is_available(self) -> bool:
        try:
            self._client.models.list()
            return True
        except Exception:
            return False


def get_llm(**kwargs) -> LocalLLM:
    return LocalLLM(**kwargs)


def _cli():
    import argparse
    ap = argparse.ArgumentParser(description="Test the local LM Studio LLM connection.")
    ap.add_argument("--check", action="store_true", help="ping the server / list models")
    ap.add_argument("--prompt", type=str, help="send a one-off prompt")
    ap.add_argument("--model", type=str, default=DEFAULT_MODEL)
    args = ap.parse_args()

    print(f"base_url = {DEFAULT_BASE_URL}")
    print(f"model    = {args.model}")
    llm = get_llm(model=args.model)
    if args.check or not args.prompt:
        ok = llm.is_available()
        print("server reachable:", ok)
        if ok:
            try:
                models = [m.id for m in llm._client.models.list().data]
                print("loaded models:", models)
            except Exception as e:
                print("could not list models:", e)
    if args.prompt:
        print("---")
        print(llm.chat(args.prompt))


if __name__ == "__main__":
    _cli()
