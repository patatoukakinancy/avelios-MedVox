# Backend

## Setup (PowerShell, from backend/)
1. `python -m venv .venv`
2. `.\.venv\Scripts\Activate.ps1`
3. `pip install -r requirements.txt`
4. `pytest -q`
5. `uvicorn app.main:app --reload`
