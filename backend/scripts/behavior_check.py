"""Behavior check against the LIVE relay (text mode). Costs real tokens: ~10 turns per patient per run.

  python scripts/behavior_check.py --patient case_01 [--patient case_02] [--runs N] [--url ws://127.0.0.1:8000]

Plays backend/scripts/behavior_scripts/<patient>.json (N sessions in a row), saves one transcript per run to
backend/logs/behavior/<patient>_<timestamp>.md and prints a PASS/WARN/FAIL table (plus an aggregate table when N > 1).
Checks are plain substring/regex, no extra model calls, and never assert exact wording:
read the transcript and judge borderline results yourself.

Script file format (all optional fields may be left out):
  "keywords": {fact_id: [kw, ...]  |  {"keywords": [kw, ...], "unlock_also": [kw, ...]}}
      leak check uses "keywords"; unlock check uses "keywords" + "unlock_also".
      A number word in a keyword also matches its digit form ("fifteen" matches "15").
  "turns": [{"say": str,
             "checks": [{"type": opening|leak|unlock|diagnosis, "fact": id, "severity": "warn"}],
             "expect_any": [kw, ...],          # check "direct-disclosure": FAIL if none appears
             "forbidden_phrases": [str, ...],  # check "forbidden-phrase": FAIL if any appears
             "subject": fact_id | [fact_id]}]  # extra subject facts for "self-contradiction"
  "self-contradiction" runs on every turn that has an unlock check (or a "subject").
"""
import argparse
import asyncio
import itertools
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from websockets.asyncio.client import connect  # noqa: E402
from websockets.exceptions import WebSocketException  # noqa: E402

from app.cases import load_case  # noqa: E402
from tests.jargon import DIAGNOSTIC_JARGON  # noqa: E402

SCRIPTS_DIR = Path(__file__).resolve().parent / "behavior_scripts"
OUT_DIR = BACKEND_DIR / "logs" / "behavior"
MAX_TURNS = 12  # cost guard
TURN_TIMEOUT = 45
MAX_SENTENCES = 2
SHORT_FRAGMENT_WORDS = 2  # a "?"/"!" fragment of this many words or fewer is not a sentence ("Pain?")
OPENING_MIN_OVERLAP = 0.4
BUSY_RETRIES = 5
STOPWORDS = {
    "the", "and", "this", "that", "with", "for", "you", "your", "are", "was", "have", "has", "had", "but",
    "not", "here", "there", "them", "they", "from", "about", "would", "could", "what", "when", "how", "its",
    "been", "all", "can", "did", "does", "out", "too",
}
NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
    "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
# Diagnosis-confirming phrases (regexes on normalised text). Jargon terms are added from tests/jargon.py.
DIAGNOSIS_PATTERNS = [r"\byes\b", r"\byou(?:'re| are) right\b", r"\bmay be right\b", r"\bprobably right\b"]
# Up to 4 words before a match: a negation within them ("not saying yes", "can't say yes") exempts the match.
NEGATION_RE = re.compile(r"(?:\bnot|n't|\bnever|\bno\b)\W+(?:\w+\W+){0,2}$")
DISCLAIMER_RE = re.compile(r"don't know|not sure|new to me|what that (?:word )?means|never heard|that word")
DENIAL_RES = [re.compile(p) for p in (
    r"\bnothing else\b", r"\b(?:i )?don't take anything else\b", r"\bno,? i (?:don't|haven't|never)\b")]
# "not really" only counts as a denial in the same sentence as a subject keyword.
SAME_SENTENCE_DENIAL_RE = re.compile(r"\bnot really\b")

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"


class RunError(Exception):
    """One run could not complete (connection problem, relay refused, timeout). Other runs continue."""

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.code = code


# ---------- text helpers ----------

def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def norm(text: str) -> str:
    return clean(text).lower().replace("’", "'").replace("‘", "'")


def sentences(text: str) -> list[str]:
    """Split on . ! ?; a <= 2-word fragment ending in ? or ! (e.g. "Pain?") does not count."""
    t = clean(text).replace("...", ", ").replace("…", ", ")
    out = []
    for part in re.split(r"(?<=[.!?])\s+", t):
        if not re.search(r"\w", part):
            continue
        if part.rstrip("\"'”’)").endswith(("?", "!")) and len(re.findall(r"\w+", part)) <= SHORT_FRAGMENT_WORDS:
            continue
        out.append(part)
    return out


def keyword_variants(keyword: str) -> set[str]:
    """The keyword plus forms where number words become digits ("fifteen" -> "15")."""
    tokens = norm(keyword).split(" ")
    options = [[t, str(NUMBER_WORDS[t])] if t in NUMBER_WORDS else [t] for t in tokens]
    return {" ".join(c) for c in itertools.product(*options)}


def _keyword_re(variant: str) -> re.Pattern:
    return re.compile(r"\b" + re.escape(variant) + (r"(?!\d)" if variant[-1:].isdigit() else ""))


def keyword_hits(text: str, keywords: list[str]) -> list[str]:
    """Keywords (as written in the script) found in text; case-insensitive, digit forms accepted."""
    n = norm(text)
    return [k for k in keywords if any(_keyword_re(v).search(n) for v in keyword_variants(k))]


def phrase_hits(text: str, phrases: list[str]) -> list[str]:
    n = norm(text)
    return [p for p in phrases if re.search(r"\b" + re.escape(norm(p)) + r"\b", n)]


def content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", norm(text)) if len(w) > 2 and w not in STOPWORDS}


def _negated(n: str, start: int) -> bool:
    window = " ".join(n[:start].split()[-4:])
    return bool(NEGATION_RE.search(window + " " if window else ""))


def term_findings(reply: str, student: str, patterns: list[str]) -> list[dict]:
    """Flagged terms in a reply. Negated matches are ignored. A term the student just said and the reply
    disclaims ("angina? that word is new to me") is a WARN ("echoed, disclaimed"); anything else is a FAIL."""
    n, s = norm(reply), norm(student)
    found = []
    for pat in patterns:
        rx = re.compile(pat)
        for m in rx.finditer(n):
            if _negated(n, m.start()):
                continue
            echoed = bool(rx.search(s))
            if echoed and DISCLAIMER_RE.search(n):
                found.append({"term": m.group(0), "status": WARN, "note": "echoed, disclaimed"})
            else:
                found.append({"term": m.group(0), "status": FAIL, "note": ""})
    return found


def jargon_patterns() -> list[str]:
    return [r"\b" + re.escape(j.lower()) + r"\b" for j in DIAGNOSTIC_JARGON]


def _status_of(findings: list[dict]) -> str:
    if any(f["status"] == FAIL for f in findings):
        return FAIL
    return WARN if findings else PASS


def _finding_detail(findings: list[dict]) -> str:
    return ", ".join(f"'{f['term']}'" + (f" ({f['note']})" if f["note"] else "") for f in findings)


# ---------- script loading ----------

def fact_keywords(script: dict, fact: str) -> tuple[list[str], list[str]]:
    """(leak keywords, unlock keywords). A plain list is used for both."""
    entry = script.get("keywords", {})[fact]
    if isinstance(entry, list):
        return entry, entry
    base = entry.get("keywords", [])
    return base, base + entry.get("unlock_also", [])


def load_script(patient: str) -> dict:
    path = SCRIPTS_DIR / f"{patient}.json"
    if not path.is_file():
        raise SystemExit(f"no behavior script for {patient}: {path}")
    script = json.loads(path.read_text(encoding="utf-8"))
    if len(script["turns"]) > MAX_TURNS:
        raise SystemExit(f"{patient}: {len(script['turns'])} turns exceeds the cost cap of {MAX_TURNS}")
    return script


# ---------- live session ----------

async def recv(ws) -> dict:
    return json.loads(await asyncio.wait_for(ws.recv(), TURN_TIMEOUT))


async def play(url: str, patient: str, turns: list[dict]) -> tuple[list[dict], dict]:
    """Returns (per-turn records, session usage). Raises RunError if the run cannot complete."""
    records: list[dict] = []
    query = urlencode({"patient_id": patient, "mode": "text"})
    async with connect(f"{url}/ws/session?{query}") as ws:
        first = await recv(ws)
        if first["type"] != "session.ready":
            raise RunError(f"could not start session: {first.get('code')} {first.get('message')}", first.get("code"))
        for turn in turns:
            await ws.send(json.dumps({"type": "text.send", "text": turn["say"]}))
            finals: list[str] = []
            final_ids: list[dict] = []
            deltas: list[str] = []
            latency = None
            error = None
            while True:
                msg = await recv(ws)
                t = msg["type"]
                if t == "transcript.final" and msg["role"] == "patient":
                    finals.append(msg["text"])
                    final_ids.append({"item_id": msg.get("item_id"), "response_id": msg.get("response_id")})
                elif t == "transcript.delta" and msg["role"] == "patient":
                    deltas.append(msg["text"])
                elif t == "latency":
                    latency = msg
                    break
                elif t == "error":
                    error = f"{msg['code']}: {msg['message']}"
                elif t == "session.ended":
                    error = f"session ended early ({msg['reason']})"
                    break
            reply = clean(" ".join(finals) if finals else "".join(deltas))
            records.append({"say": turn["say"], "checks": turn.get("checks", []), "reply": reply,
                            "expect_any": turn.get("expect_any", []),
                            "forbidden_phrases": turn.get("forbidden_phrases", []),
                            "subject": turn.get("subject", []),
                            "final_ids": final_ids, "latency": latency, "error": error})
            print(f"\n> {turn['say']}\n< {reply or '(no reply)'}")
            if error and latency is None:
                break
        await ws.send(json.dumps({"type": "session.end"}))
        usage: dict = {}
        while True:
            msg = await recv(ws)
            if msg["type"] == "session.ended":
                usage = msg.get("usage") or {}
                break
    return records, usage


async def play_with_retry(url: str, patient: str, turns: list[dict]) -> tuple[list[dict], dict]:
    """The previous run's session may still be releasing the one-session lock: retry "busy" briefly."""
    for attempt in range(BUSY_RETRIES + 1):
        try:
            return await play(url, patient, turns)
        except RunError as exc:
            if exc.code != "busy" or attempt == BUSY_RETRIES:
                raise
            await asyncio.sleep(0.5)
    raise AssertionError("unreachable")


# ---------- evaluation ----------

def denial_hits(reply: str, subject_keywords: list[str]) -> list[str]:
    """Denial patterns in a reply; "not really" only when its sentence also names a subject keyword."""
    n = norm(reply)
    found = [rx.pattern for rx in DENIAL_RES if rx.search(n)]
    if any(SAME_SENTENCE_DENIAL_RE.search(norm(s)) and keyword_hits(s, subject_keywords) for s in sentences(reply)):
        found.append(SAME_SENTENCE_DENIAL_RE.pattern)
    return found


def _row(check: str, turn, status: str, detail: str = "") -> dict:
    return {"check": check, "turn": turn, "status": status, "detail": detail}


def _apply_severity(status: str, check: dict) -> str:
    return WARN if status == FAIL and check.get("severity") == "warn" else status


def evaluate(patient: str, script: dict, records: list[dict], opening_line: str | None = None) -> list[dict]:
    """Rows: {check, turn, status (PASS|WARN|FAIL), detail}. length/jargon are one aggregated row each."""
    if opening_line is None:
        opening_line = load_case(patient).osce_behavior.opening_line
    replies = [clean(r.get("reply", "")) for r in records]
    rows: list[dict] = []

    long_turns = [(i, len(sentences(rep))) for i, rep in enumerate(replies, start=1) if len(sentences(rep)) > MAX_SENTENCES]
    rows.append(_row(f"length (<= {MAX_SENTENCES} sentences)", "all", FAIL if long_turns else PASS,
                     ", ".join(f"turn {i}: {n} sentences" for i, n in long_turns)))

    jar = [(i, term_findings(rep, rec.get("say", ""), jargon_patterns())) for i, (rec, rep) in enumerate(zip(records, replies), start=1)]
    jar = [(i, f) for i, f in jar if f]
    rows.append(_row("jargon", "all", _status_of([x for _, f in jar for x in f]),
                     ", ".join(f"turn {i}: {_finding_detail(f)}" for i, f in jar)))

    for i, (rec, rep) in enumerate(zip(records, replies), start=1):
        for c in rec.get("checks", []):
            kind, fact = c["type"], c.get("fact")
            if kind == "leak":
                hits = keyword_hits(rep, fact_keywords(script, fact)[0])
                rows.append(_row(f"leak: {fact}", i, _apply_severity(FAIL if hits else PASS, c),
                                 f"leaked: {hits}" if hits else ""))
            elif kind == "unlock":
                hits = keyword_hits(rep, fact_keywords(script, fact)[1])
                rows.append(_row(f"unlock: {fact}", i, _apply_severity(PASS if hits else FAIL, c),
                                 f"matched: {hits}" if hits else "no keyword found"))
            elif kind == "diagnosis":
                found = term_findings(rep, rec.get("say", ""), DIAGNOSIS_PATTERNS + jargon_patterns())
                rows.append(_row("diagnosis", i, _apply_severity(_status_of(found), c), _finding_detail(found)))
            elif kind == "opening":
                want = content_words(opening_line)
                shared = want & content_words(rep)
                ratio = len(shared) / len(want) if want else 0.0
                rows.append(_row("opening", i, _apply_severity(PASS if ratio >= OPENING_MIN_OVERLAP else FAIL, c),
                                 f"{len(shared)}/{len(want)} content words shared ({ratio:.0%})"))

        if rec.get("expect_any"):
            hits = keyword_hits(rep, rec["expect_any"])
            rows.append(_row("direct-disclosure", i, PASS if hits else FAIL,
                             f"matched: {hits}" if hits else f"none of {rec['expect_any']} found"))

        subject = rec.get("subject", [])
        subjects = [c["fact"] for c in rec.get("checks", []) if c["type"] == "unlock"]
        subjects += [subject] if isinstance(subject, str) else list(subject)
        if subjects:
            # base keywords only: the broader unlock_also words are too generic to prove a contradiction
            base = [k for f in dict.fromkeys(subjects) for k in fact_keywords(script, f)[0]]
            hits = keyword_hits(rep, base)
            denials = denial_hits(rep, base)
            bad = bool(denials and hits)
            rows.append(_row("self-contradiction", i, FAIL if bad else PASS,
                             f"denial {denials} + keyword {hits}" if bad else ""))

        if rec.get("forbidden_phrases"):
            hits = phrase_hits(rep, rec["forbidden_phrases"])
            rows.append(_row("forbidden-phrase", i, FAIL if hits else PASS, f"found: {hits}" if hits else ""))

        if rec.get("error"):
            rows.append(_row("relay error", i, FAIL, rec["error"]))
    return rows


# ---------- output ----------

def render_table(rows: list[dict]) -> str:
    lines = [f"{'check':<30} {'turn':<5} {'result':<7} detail", "-" * 78]
    for r in rows:
        lines.append(f"{r['check']:<30} {str(r['turn']):<5} {r['status']:<7} {r['detail']}")
    return "\n".join(lines)


def _label(row: dict) -> str:
    return row["check"] if row["turn"] == "all" else f"{row['check']} (turn {row['turn']})"


def aggregate(runs_rows: list[list[dict]], n_runs: int) -> list[dict]:
    """One row per check label: pass count (out of n_runs), warn, fail. Errored runs contribute no rows."""
    table: dict[str, dict] = {}
    for rows in runs_rows:
        for r in rows:
            e = table.setdefault(_label(r), {"check": _label(r), "pass": 0, "warn": 0, "fail": 0})
            e[r["status"].lower()] += 1
    return list(table.values())


def render_aggregate(agg: list[dict], n_runs: int, run_errors: int) -> str:
    lines = [f"{'check':<44} {'pass':<7} {'warn':<5} {'fail':<5}", "-" * 64]
    for e in agg:
        lines.append(f"{e['check']:<44} {e['pass']}/{n_runs:<5} {e['warn']:<5} {e['fail']:<5}")
    if run_errors:
        lines.append(f"run errors (not counted above): {run_errors} of {n_runs}")
    return "\n".join(lines)


def save_transcript(patient: str, records: list[dict], rows: list[dict], usage: dict, suffix: str = "") -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{patient}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{suffix}.md"
    out = [f"# Behavior check: {patient}", ""]
    for i, r in enumerate(records, start=1):
        out += [f"## Turn {i}", f"**Student:** {r['say']}", "", f"**Patient:** {r['reply'] or '(no reply)'}", ""]
        for j, ids in enumerate(r.get("final_ids") or [], start=1):
            out.append(f"_final {j}: item_id={ids.get('item_id')} response_id={ids.get('response_id')}_")
        if r.get("final_ids"):
            out.append("")
        lat = r.get("latency") or {}
        names = [c["type"] + (f"({c['fact']})" if c.get("fact") else "") for c in r.get("checks", [])]
        names += [k for k in ("expect_any", "forbidden_phrases") if r.get(k)]
        out.append(f"_sentences={len(sentences(r['reply']))} ttft_ms={lat.get('ttft_ms')}_ checks: "
                   + (", ".join(names) or "length/jargon only"))
        out.append("")
    out += ["## Results", "", "```", render_table(rows), "```", "", f"Usage: `{json.dumps(usage)}`", ""]
    path.write_text("\n".join(out), encoding="utf-8")
    return path


def usage_summary(usage: dict) -> str:
    cached = (usage.get("input_token_details") or {}).get("cached_tokens", 0)
    return (f"total_tokens={usage.get('total_tokens', 0)} input={usage.get('input_tokens', 0)} "
            f"(cached {cached}) output={usage.get('output_tokens', 0)}")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Scripted behavior check against the live relay (text mode).")
    ap.add_argument("--patient", action="append", required=True, help="repeatable")
    ap.add_argument("--url", default="ws://127.0.0.1:8000")
    ap.add_argument("--runs", type=int, default=1, help="sessions to run in a row per patient (default 1)")
    return ap


async def main() -> int:
    a = build_parser().parse_args()
    if a.runs < 1:
        raise SystemExit("--runs must be at least 1")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    bad = False
    grand: dict = {"total_tokens": 0, "input_tokens": 0, "output_tokens": 0, "input_token_details": {"cached_tokens": 0}}
    for patient in a.patient:
        script = load_script(patient)
        runs_rows: list[list[dict]] = []
        run_errors = 0
        for n in range(1, a.runs + 1):
            print(f"\n===== {patient}: run {n}/{a.runs}, {len(script['turns'])} turns =====")
            try:
                records, usage = await play_with_retry(a.url, patient, script["turns"])
            except (RunError, OSError, asyncio.TimeoutError, WebSocketException) as exc:
                run_errors += 1
                bad = True
                print(f"\n[run error] {type(exc).__name__}: {exc}")
                continue
            rows = evaluate(patient, script, records)
            runs_rows.append(rows)
            path = save_transcript(patient, records, rows, usage, suffix=f"_run{n}" if a.runs > 1 else "")
            print(f"\n--- {patient} run {n} results ---\n{render_table(rows)}")
            print(f"usage: {usage_summary(usage)}\ntranscript: {path}")
            bad = bad or any(r["status"] == FAIL for r in rows)
            for k in ("total_tokens", "input_tokens", "output_tokens"):
                grand[k] += usage.get(k, 0)
            grand["input_token_details"]["cached_tokens"] += (usage.get("input_token_details") or {}).get("cached_tokens", 0)
        if a.runs > 1:
            print(f"\n=== {patient}: aggregate over {a.runs} runs ===\n"
                  f"{render_aggregate(aggregate(runs_rows, a.runs), a.runs, run_errors)}")
    print(f"\nTOTAL usage: {usage_summary(grand)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
