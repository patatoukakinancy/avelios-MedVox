"""Pydantic v2 model of schema/patient_case.schema.json.

The JSON Schema stays the source of truth; tests validate the case files against both.
"""
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

Text = Field(min_length=1)
FACT_ID_PATTERN = r"^[a-z0-9_]+$"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PublicCard(_Strict):
    display_name: str = Text
    age: int = Field(ge=0, le=120)
    sex: Literal["female", "male"]
    setting: str = Text
    presenting_complaint: str = Text
    difficulty: Literal["easy", "medium", "hard"]
    estimated_minutes: int = Field(ge=1)


class Fact(_Strict):
    id: str = Field(pattern=FACT_ID_PATTERN)
    category: Literal[
        "presenting_complaint",
        "associated_symptom",
        "pertinent_negative",
        "past_medical_history",
        "medication",
        "allergy",
        "family_history",
        "social_history",
    ]
    truth: str = Text
    patient_says: str = Text
    disclosure: Literal["spontaneous", "open_question", "direct_question", "specific_follow_up"]
    first_answer: Optional[str] = Field(default=None, min_length=1)
    reveal_when: Optional[str] = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _check_follow_up(self) -> "Fact":
        if self.disclosure == "specific_follow_up":
            if self.first_answer is None or self.reveal_when is None:
                raise ValueError("specific_follow_up needs first_answer and reveal_when")
        elif self.reveal_when is not None:
            raise ValueError("reveal_when is only allowed on specific_follow_up facts")
        return self


class ClinicalBackground(_Strict):
    occupation: str = Text
    social_context: str = Text
    facts: list[Fact] = Field(min_length=1)


class Voice(_Strict):
    voice_id: str = Text
    tone_instructions: str = Text


class IdeasConcernsExpectations(_Strict):
    ideas: str = Text
    concerns: str = Text
    expectations: str = Text


class EmotionalCue(_Strict):
    trigger: str = Text
    reaction: str = Text
    reveals_fact_ids: list[str]

    @model_validator(mode="after")
    def _check_ids(self) -> "EmotionalCue":
        import re

        for fid in self.reveals_fact_ids:
            if not re.match(FACT_ID_PATTERN, fid):
                raise ValueError(f"bad fact id {fid!r}")
        if len(set(self.reveals_fact_ids)) != len(self.reveals_fact_ids):
            raise ValueError("reveals_fact_ids must be unique")
        return self


class OsceBehavior(_Strict):
    personality: str = Text
    speaking_style: str = Text
    emotional_state: str = Text
    voice: Voice
    opening_line: str = Text
    ideas_concerns_expectations: IdeasConcernsExpectations
    emotional_cues: list[EmotionalCue]
    question_for_doctor: str = Text
    reaction_to_plan: str = Text
    unknown_question_response: str = Text


class PatientCase(_Strict):
    schema_version: Literal["1.0"]
    patient_id: str = Field(pattern=r"^case_[0-9]{2}$")
    public_card: PublicCard
    clinical_background: ClinicalBackground
    osce_behavior: OsceBehavior

    @model_validator(mode="after")
    def _cross_references(self) -> "PatientCase":
        ids = [f.id for f in self.clinical_background.facts]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"duplicate fact ids: {dupes}")
        known = set(ids)
        for cue in self.osce_behavior.emotional_cues:
            missing = [i for i in cue.reveals_fact_ids if i not in known]
            if missing:
                raise ValueError(f"emotional cue reveals unknown fact ids: {missing}")
        return self
