from fastapi import FastAPI

from .cases import list_patients

app = FastAPI(title="Standardized Patient Voice Simulator")


@app.get("/patients")
def get_patients() -> list[dict]:
    """[{patient_id, public_card}] only. Hidden clinical data never leaves the backend."""
    return list_patients()
