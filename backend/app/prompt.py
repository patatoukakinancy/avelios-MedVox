"""Build the patient system prompt from schema/patient_system_prompt.md.

Deterministic: same case in -> byte-identical prompt out (prompt-cache friendly).
Never includes fact `truth`.
"""
import json
from pathlib import Path

from .cases import REPO_ROOT
from .models import PatientCase

TEMPLATE_PATH = REPO_ROOT / "schema" / "patient_system_prompt.md"
FACT_KEYS = ("id", "category", "patient_says", "disclosure", "first_answer", "reveal_when")


def _compact(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def load_template(path: Path = TEMPLATE_PATH) -> str:
    """Text of the first fenced block under '## Template'."""
    lines = path.read_text(encoding="utf-8").splitlines()
    try:
        start = lines.index("## Template")
    except ValueError:
        raise ValueError("'## Template' heading not found") from None
    block: list[str] = []
    inside = False
    for line in lines[start + 1 :]:
        if not inside:
            if line.startswith("```"):
                inside = True
            continue
        if line.startswith("```"):
            return "\n".join(block)
        block.append(line)
    raise ValueError("fenced template block not found or not closed")


def render_prompt(case: PatientCase, template: str | None = None) -> str:
    template = load_template() if template is None else template
    card = case.public_card
    bg = case.clinical_background
    behavior = case.osce_behavior.model_dump(exclude={"voice"})
    facts = [
        {k: v for k, v in f.model_dump().items() if k in FACT_KEYS and v is not None}
        for f in bg.facts
    ]
    replacements = [
        ("{display_name}", card.display_name),
        ("{age}", str(card.age)),
        ("{sex}", card.sex),
        ("{setting}", card.setting),
        ("{occupation}", bg.occupation),
        ("{social_context}", bg.social_context),
        ("{tone_instructions}", case.osce_behavior.voice.tone_instructions),
        ("{osce_behavior}", _compact(behavior)),
        ("{facts}", _compact(facts)),
    ]
    out = template
    for placeholder, value in replacements:
        out = out.replace(placeholder, value)
    return out
