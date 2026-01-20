"""
draft_report.py

Generates a structured incident report (Markdown) from computed metrics.

This module is the first LLM step in the reporting layer:
- Input: metrics (Python dict loaded from artifacts/metrics.json)
- Contract: docs/report/report_schema.md (required sections + ordering)
- Guardrails: docs/report/grounding_rules.md (no invented facts; metrics-only)

Design goals:
- Grounded: the model may only reference information present in metrics
- Consistent: low temperature + strict formatting instructions
- Auditable: the full prompt is deterministic given (schema, rules, metrics)

This mirrors the "structured summarization + consistency enforcement" approach
described in the Phase 2 design philosophy. :contentReference[oaicite:2]{index=2}
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

# If you're using the official OpenAI Python SDK (recommended), install:
#   pip install openai
#
# This file is written for the modern SDK style (OpenAI() client).
# If you aren't ready to install it yet, you can stub out the call_llm() method.
try:
    from openai import OpenAI  # type: ignore
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore


DEFAULT_SCHEMA_PATH = Path("docs/report/report_schema.md")
DEFAULT_RULES_PATH = Path("docs/report/grounding_rules.md")


@dataclass(frozen=True)
class DraftReportConfig:
    """
    Configuration for draft report generation.

    model:
      OpenAI model name (e.g., "gpt-4.1-mini", "gpt-4o-mini", etc.)
    temperature:
      Keep low for repeatability.
    max_output_tokens:
      Prevent runaway outputs.
    schema_path / rules_path:
      Paths to the report contract and grounding rules.
    """
    model: str = "gpt-4o-mini"
    temperature: float = 0.2
    max_output_tokens: int = 900
    schema_path: Path = DEFAULT_SCHEMA_PATH
    rules_path: Path = DEFAULT_RULES_PATH


def _read_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    return path.read_text(encoding="utf-8")


def _format_metrics(metrics: Dict[str, Any]) -> str:
    """
    Render metrics in a stable, JSON-formatted block so the model has an exact
    source of truth.
    """
    return json.dumps(metrics, indent=2, sort_keys=True)


def build_prompt(*, schema: str, rules: str, metrics_json: str) -> tuple[str, str]:
    """
    Returns (system_prompt, user_prompt).
    We keep the contract (schema + rules) in the prompt so the LLM has no excuse
    to improvise structure or invent facts.
    """
    system_prompt = (
        "You are an incident report generator.\n"
        "You produce clear, professional incident reports for engineers.\n"
        "You MUST follow the provided report schema exactly.\n"
        "You MUST follow the provided grounding rules exactly.\n"
        "If a required detail is not present in the metrics JSON, you must say it is not available.\n"
        "Do not add extra sections. Do not reorder sections."
    )

    user_prompt = (
        "## Report Schema (contract)\n"
        f"{schema}\n\n"
        "## Grounding Rules (must obey)\n"
        f"{rules}\n\n"
	"## Executive Summary Requirements (hard constraints)\n"
    	"- The Executive Summary MUST reference only the peak incident window.\n"
    	"- It MUST include:\n"
    	"  - peak window start time\n"
    	"  - peak window end time\n"
    	"  - peak window total_requests\n"
    	"  - peak window 5xx_count\n"
    	"  - peak window 5xx_rate\n"
    	"- Do NOT mention overall dataset rates unless explicitly labeled as 'overall' and present in metrics.json.\n"
    	"- Do NOT compute new rates or ratios.\n"
    	"- Do NOT infer traffic changes (e.g., 'increased traffic') unless a baseline comparison is explicitly provided in metrics.json.\n"
    	"- Do NOT describe endpoints as 'user-facing' or infer business impact.\n"
    	"- If required information is not available, state 'Not available from metrics.'\n\n"
        "## Metrics JSON (only source of factual truth)\n"
        "```json\n"
        f"{metrics_json}\n"
        "```\n\n"
	"CRITICAL FORMAT RULES:\n"
        "- Use the section headings EXACTLY as shown below (character-for-character).\n"
        "- Do NOT add numbering like '1.', '2.', etc.\n"
        "- Each heading must appear exactly once.\n"
        "Required headings (exact):\n"
        "## Executive Summary\n"
        "## Incident Window\n"
        "## Impact\n"
        "## Hotspots\n"
        "## Traffic Context\n"
        "## Likely Explanation\n"
        "## Recommended Next Checks\n"
	"IMPORTANT:\n"
        "- Use the headings exactly as written. Do not add extra words (e.g., do NOT write 'Impact Overview' or 'Error Hotspots').\n"
        "- The headings must be exactly: '## Impact' and '## Hotspots'.\n"
	"Traffic Context section rules:\n"
        "- If traffic.baseline_5m.typical_requests_5m is present, describe what a typical"
        "5-minute window looks like using that value.\n"
        "- Compare it directly to errors.peak_5xx_window_5m.total_requests using the exact"
        "numbers provided in metrics.json.\n"
        "- Use traffic_multiplier_vs_typical if present; do NOT compute new ratios.\n"
        "- Do NOT describe a traffic surge unless traffic_multiplier_vs_typical is"
        "meaningfully greater than 1.0.\n"
        "- If baseline traffic metrics are not present, explicitly state that baseline"
        "comparison is not available.\n"
	"Time formatting rule:\n"
        "- When reporting window_start and window_end, copy them EXACTLY from metrics.json,"
        "including the timezone offset (e.g., +00:00).\n"
        "Now generate the incident report in Markdown.\n"
        "Requirements:\n"
        "- Use the exact section headings and ordering from the schema.\n"
        "- Keep language cautious (e.g., 'suggests', 'is consistent with').\n"
        "- Every number, endpoint, and time window MUST come from the metrics JSON.\n"
        "- Be concise but complete.\n"
	"Hard constraints:\n"
	"- Do NOT compute new rates unless the numerator and denominator are both explicitly present in metrics.json.\n"
	"- If you mention a rate, label it clearly as either 'peak window' or 'overall', and use the exact value from metrics.json.\n"
	"- Do NOT claim traffic increased/decreased unless metrics.json explicitly provides a baseline comparison.\n"
	"- Do NOT describe endpoints as 'user-facing' or infer business impact. Only describe observed failures and where they occurred.\n"
	"- If a detail is not present in metrics.json, write 'Not available from metrics.'\n"
    )

    return system_prompt, user_prompt


def call_llm_openai(
    *,
    system_prompt: str,
    user_prompt: str,
    config: DraftReportConfig,
) -> str:
    """
    Call OpenAI chat completion and return the report text.

    Requires:
      - openai package installed
      - OPENAI_API_KEY set in environment
    """
    if OpenAI is None:
        raise RuntimeError(
            "OpenAI SDK is not installed. Run: pip install openai"
        )

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set in your environment.")

    client = OpenAI(api_key=api_key)

    # Note: parameter names may vary slightly by SDK version; this pattern is common
    # for the modern OpenAI python client.
    resp = client.chat.completions.create(
        model=config.model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=config.temperature,
        max_tokens=config.max_output_tokens,
    )

    content = resp.choices[0].message.content
    if not content:
        raise RuntimeError("LLM returned empty content.")
    return content.strip()


def generate_draft_report(
    metrics: Dict[str, Any],
    *,
    config: Optional[DraftReportConfig] = None,
) -> str:
    """
    Generate a draft incident report (Markdown) from computed metrics.

    This function:
      1) loads schema + grounding rules from docs/
      2) embeds them + metrics JSON into a strict prompt
      3) calls the LLM with low temperature
      4) returns Markdown report text
    """
    cfg = config or DraftReportConfig()

    schema = _read_text(cfg.schema_path)
    rules = _read_text(cfg.rules_path)
    metrics_json = _format_metrics(metrics)

    system_prompt, user_prompt = build_prompt(
        schema=schema,
        rules=rules,
        metrics_json=metrics_json,
    )

    return call_llm_openai(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        config=cfg,
    )
