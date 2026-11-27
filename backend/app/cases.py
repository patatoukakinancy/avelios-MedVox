"""Load patient cases from <repo root>/cases/{patient_id}.json."""
import json
import re
from pathlib import Path

from .models import PatientCase

REPO_ROOT = Path(__file__).resolve().parents[2]
CASES_DIR = REPO_ROOT / "cases"
PATIENT_ID_RE = re.compile(r"^case_[0-9]{2}$")


class InvalidPatientId(ValueError):
    pass


class CaseNotFound(LookupError):
    pass


def load_case(patient_id: str, cases_dir: Path = CASES_DIR) -> PatientCase:
    if not isinstance(patient_id, str) or not PATIENT_ID_RE.fullmatch(patient_id):
        raise InvalidPatientId("patient_id must match case_NN")
    path = cases_dir / f"{patient_id}.json"
    if not path.is_file():
        raise CaseNotFound(patient_id)
    with path.open(encoding="utf-8") as f:
        case = PatientCase.model_validate(json.load(f))
    if case.patient_id != patient_id:
        raise ValueError(f"{path.name}: patient_id does not match file name")
    return case


def list_patient_ids(cases_dir: Path = CASES_DIR) -> list[str]:
    return sorted(p.stem for p in cases_dir.glob("case_*.json") if PATIENT_ID_RE.fullmatch(p.stem))


def list_patients(cases_dir: Path = CASES_DIR) -> list[dict]:
    """Frontend-safe listing: patient_id and public_card only."""
    out = []
    for pid in list_patient_ids(cases_dir):
        case = load_case(pid, cases_dir)
        out.append({"patient_id": case.patient_id, "public_card": case.public_card.model_dump()})
    return out
