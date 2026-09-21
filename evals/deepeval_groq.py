"""Groq judge model for DeepEval, reusing the project's GROQ_API_KEY.

Uses llama-3.1-8b-instant: cheap, fast, good enough for scoring whether
a diff addresses the reported bug. Sandbox pass/fail remains the primary
verdict; the GEval score is a secondary signal.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api" / "src"))

from deepeval.models import DeepEvalBaseLLM  # noqa: E402

JUDGE_MODEL = "openai/gpt-oss-20b"


class GroqJudgeLLM(DeepEvalBaseLLM):
    def __init__(self, model_name: str = JUDGE_MODEL):
        self.model_name = model_name
        key = os.environ.get("GROQ_API_KEY", "")
        if not key:
            # Also honor root .env like the API does.
            env_file = Path(__file__).resolve().parents[1] / ".env"
            if env_file.exists():
                for line in env_file.read_text().splitlines():
                    if line.startswith("GROQ_API_KEY="):
                        key = line.split("=", 1)[1].strip()
                        break
        if not key:
            raise RuntimeError("GROQ_API_KEY is not set; cannot judge")
        from groq import Groq

        self.client = Groq(api_key=key)

    def load_model(self):
        return self.client

    def generate(self, prompt: str, *args, **kwargs) -> str:
        resp = self.client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=1024,
        )
        return (resp.choices[0].message.content or "").strip()

    async def a_generate(self, prompt: str, *args, **kwargs) -> str:
        return self.generate(prompt, *args, **kwargs)

    def get_model_name(self, *args, **kwargs) -> str:
        return self.model_name
