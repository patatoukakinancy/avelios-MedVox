import copy
import json
import re

import jsonschema
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.cases import CASES_DIR, REPO_ROOT, InvalidPatientId, CaseNotFound, list_patient_ids, load_case
from app.main import app
from app.models import PatientCase
from app.prompt import load_template, render_prompt
from tests.jargon import DIAGNOSTIC_JARGON

CASE_IDS = ["case_01", "case_02"]
SCHEMA = json.loads((REPO_ROOT / "schema" / "patient_case.schema.json").read_text(encoding="utf-8"))


def _raw(pid):
    return json.loads((CASES_DIR / f"{pid}.json").read_text(encoding="utf-8"))


def test_case_files_present():
    assert list_patient_ids() == CASE_IDS


@pytest.mark.parametrize("pid", CASE_IDS)
def test_case_validates_with_pydantic(pid):
    assert load_case(pid).patient_id == pid


@pytest.mark.parametrize("pid", CASE_IDS)
def test_case_validates_with_jsonschema(pid):
    jsonschema.validate(_raw(pid), SCHEMA)


def test_broken_case_duplicate_fact_id():
    raw = _raw("case_01")
    raw["clinical_background"]["facts"].append(copy.deepcopy(raw["clinical_background"]["facts"][0]))
    with pytest.raises(ValidationError, match="duplicate fact ids"):
        PatientCase.model_validate(raw)


def test_broken_case_unknown_reveals_fact_id():
    raw = _raw("case_01")
    cues = raw["osce_behavior"]["emotional_cues"]
    assert cues, "case_01 should have emotional cues"
    cues[0]["reveals_fact_ids"] = ["does_not_exist"]
    with pytest.raises(ValidationError, match="unknown fact ids"):
        PatientCase.model_validate(raw)


def test_broken_case_follow_up_rules():
    raw = _raw("case_01")
    fact = raw["clinical_background"]["facts"][0]
    fact["disclosure"] = "specific_follow_up"
    fact.pop("reveal_when", None)
    with pytest.raises(ValidationError):
        PatientCase.model_validate(raw)
    raw = _raw("case_01")
    raw["clinical_background"]["facts"][1]["reveal_when"] = "x"  # not a specific_follow_up fact
    with pytest.raises(ValidationError):
        PatientCase.model_validate(raw)


def test_extra_fields_forbidden():
    raw = _raw("case_01")
    raw["public_card"]["secret"] = "x"
    with pytest.raises(ValidationError):
        PatientCase.model_validate(raw)


@pytest.mark.parametrize("bad", ["../x", "case_1", "case_001", "CASE_01", "case_01.json", "", "case_01/../case_02"])
def test_invalid_patient_id_rejected(bad):
    with pytest.raises(InvalidPatientId):
        load_case(bad)


def test_missing_case_not_found():
    with pytest.raises(CaseNotFound):
        load_case("case_99")


@pytest.mark.parametrize("pid", CASE_IDS)
def test_prompt_has_no_truth(pid):
    case = load_case(pid)
    prompt = render_prompt(case)
    for fact in case.clinical_background.facts:
        assert fact.truth not in prompt
    assert '"truth"' not in prompt


@pytest.mark.parametrize("pid", CASE_IDS)
def test_prompt_has_no_diagnostic_jargon(pid):
    prompt = render_prompt(load_case(pid)).lower()
    found = [t for t in DIAGNOSTIC_JARGON if t in prompt]
    assert not found, found


@pytest.mark.parametrize("pid", CASE_IDS)
def test_prompt_has_no_unreplaced_placeholders(pid):
    prompt = render_prompt(load_case(pid))
    template = load_template()
    for name in set(re.findall(r"\{[a-z_]+\}", template)):
        assert name not in prompt, name


@pytest.mark.parametrize("pid", CASE_IDS)
def test_tone_appears_exactly_once_and_not_in_behavior(pid):
    case = load_case(pid)
    prompt = render_prompt(case)
    tone = case.osce_behavior.voice.tone_instructions
    assert prompt.count(tone) == 1
    assert "tone_instructions" not in prompt
    assert "voice_id" not in prompt


@pytest.mark.parametrize("pid", CASE_IDS)
def test_prompt_deterministic(pid):
    case = load_case(pid)
    assert render_prompt(case).encode("utf-8") == render_prompt(load_case(pid)).encode("utf-8")


@pytest.mark.parametrize("pid", CASE_IDS)
def test_facts_in_file_order_and_reduced(pid):
    case = load_case(pid)
    prompt = render_prompt(case)
    facts_json = prompt.split("FACTS: ", 1)[1]
    facts = json.loads(facts_json)
    assert [f["id"] for f in facts] == [f.id for f in case.clinical_background.facts]
    allowed = {"id", "category", "patient_says", "disclosure", "first_answer", "reveal_when"}
    assert all(set(f) <= allowed for f in facts)
    assert all("first_answer" not in f or f["first_answer"] for f in facts)


def test_prompt_lengths_summary(capsys):
    with capsys.disabled():
        for pid in CASE_IDS:
            print(f"\n[prompt length] {pid}: {len(render_prompt(load_case(pid)))} chars")


def test_patients_endpoint_is_public_only():
    client = TestClient(app)
    res = client.get("/patients")
    assert res.status_code == 200
    data = res.json()
    assert [p["patient_id"] for p in data] == CASE_IDS
    for p in data:
        assert set(p) == {"patient_id", "public_card"}
        assert set(p["public_card"]) == {
            "display_name", "age", "sex", "setting", "presenting_complaint", "difficulty", "estimated_minutes",
        }
    body = res.text
    for forbidden in ("clinical_background", "osce_behavior", "opening_line", "truth", "voice"):
        assert forbidden not in body
