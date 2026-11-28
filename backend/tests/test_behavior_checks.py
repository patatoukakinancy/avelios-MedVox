"""Offline unit tests for scripts/behavior_check.py using fabricated replies (no network, no model calls)."""
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import behavior_check as bc  # noqa: E402

OPENING = "Probably just indigestion. My daughter booked this, so here I am."

SCRIPT = {
    "keywords": {
        "smoking": ["fifteen", "since i was twenty"],
        "bp": {"keywords": ["amlodipine", "five milligram"], "unlock_also": ["miss", "every day"]},
        "sildenafil": ["sildenafil", "online"],
        "mood": ["peter", "evenings"],
    }
}


def rec(reply, say="Q?", checks=(), **extra):
    return {"say": say, "reply": reply, "checks": list(checks), "latency": None, "error": None, **extra}


def run(records, script=SCRIPT):
    return bc.evaluate("case_01", script, records, opening_line=OPENING)


def row(rows, check, turn=None):
    found = [r for r in rows if r["check"] == check and (turn is None or r["turn"] == turn)]
    assert len(found) == 1, (check, turn, rows)
    return found[0]


# ---------- 1. whitespace ----------

def test_clean_whitespace():
    assert bc.clean("  Hello  \n there\t you  ") == "Hello there you"


def test_evaluate_cleans_replies_before_checks():
    rows = run([rec("I smoke about\n fifteen   a day.", checks=[{"type": "unlock", "fact": "smoking"}])])
    assert row(rows, "unlock: smoking")["status"] == bc.PASS


# ---------- 2. sentence counting ----------

def test_short_question_fragment_is_not_a_sentence():
    assert len(bc.sentences("Pain? Oh no, dear, no pain.")) == 1
    assert len(bc.sentences("Really! That is odd.")) == 1


def test_real_sentences_still_counted():
    assert len(bc.sentences("Is it bad today? It comes and goes. I sit down.")) == 3
    assert len(bc.sentences("Fine. Okay.")) == 2  # a period-ended fragment still counts


def test_length_check_uses_adjusted_count():
    ok = run([rec("Pain? Oh no, dear. No pain at all.")])
    assert row(ok, f"length (<= {bc.MAX_SENTENCES} sentences)")["status"] == bc.PASS
    long = run([rec("One thing. Two things. Three things.")])
    assert row(long, f"length (<= {bc.MAX_SENTENCES} sentences)")["status"] == bc.FAIL


# ---------- 3. keywords: case and digit variants ----------

@pytest.mark.parametrize("reply,kw", [
    ("I smoke about 15 a day.", "fifteen"),
    ("I smoke about FIFTEEN a day.", "fifteen"),
    ("Since I was 20.", "since i was twenty"),
    ("Amlodipine, 5 milligrams.", "five milligram"),
    ("It was 4 out of 10.", "four out of ten"),
])
def test_digit_and_case_variants_match(reply, kw):
    assert bc.keyword_hits(reply, [kw]) == [kw]


def test_digit_variant_does_not_match_longer_number():
    assert bc.keyword_hits("About 150 a day.", ["fifteen"]) == []
    assert bc.keyword_hits("I get 15 a day.", ["fifteen"]) == ["fifteen"]


def test_digit_forms_work_in_leak_and_unlock():
    leak = run([rec("Oh, around 15.", checks=[{"type": "leak", "fact": "smoking"}])])
    assert row(leak, "leak: smoking")["status"] == bc.FAIL
    unlock = run([rec("Around 15.", checks=[{"type": "unlock", "fact": "smoking"}])])
    assert row(unlock, "unlock: smoking")["status"] == bc.PASS


def test_unlock_also_only_applies_to_unlock():
    reply = "I miss it some days."
    leak = run([rec(reply, checks=[{"type": "leak", "fact": "bp"}])])
    assert row(leak, "leak: bp")["status"] == bc.PASS
    unlock = run([rec(reply, checks=[{"type": "unlock", "fact": "bp"}])])
    assert row(unlock, "unlock: bp")["status"] == bc.PASS


# ---------- 4. diagnosis / jargon: negation, echo ----------

@pytest.mark.parametrize("reply", [
    "I'm not saying yes to that.",
    "I can't say yes, dear.",
    "I can’t say yes.",  # curly apostrophe
    "I never said yes.",
    "No, I don't know what angina is.",
    "Not sure what angina means.",
])
def test_negated_terms_are_not_flagged(reply):
    rows = run([rec(reply, say="Is it angina?", checks=[{"type": "diagnosis"}])])
    assert row(rows, "diagnosis")["status"] == bc.PASS
    assert row(rows, "jargon")["status"] == bc.PASS


def test_confirmation_fails():
    rows = run([rec("Yes, I suppose it is.", say="Is it angina?", checks=[{"type": "diagnosis"}])])
    assert row(rows, "diagnosis")["status"] == bc.FAIL
    rows = run([rec("You're right, it is my heart.", say="I think it's your heart.", checks=[{"type": "diagnosis"}])])
    assert row(rows, "diagnosis")["status"] == bc.FAIL


@pytest.mark.parametrize("reply", ["I think you may be right", "You're probably right, doctor.", "You are right."])
def test_real_agreement_fails_diagnosis(reply):
    rows = run([rec(reply, say="Could this be your heart?", checks=[{"type": "diagnosis"}])])
    assert row(rows, "diagnosis")["status"] == bc.FAIL


def test_real_i_hope_not_passes_diagnosis():
    rows = run([rec("I hope not", say="Could this be your heart?", checks=[{"type": "diagnosis"}])])
    assert row(rows, "diagnosis")["status"] == bc.PASS


def test_word_boundaries():
    rows = run([rec("Yesterday it was worse.", say="Is it angina?", checks=[{"type": "diagnosis"}])])
    assert row(rows, "diagnosis")["status"] == bc.PASS


def test_echoed_and_disclaimed_is_warn():
    rows = run([rec("Angina? That word is new to me.", say="Is it angina?", checks=[{"type": "diagnosis"}])])
    d = row(rows, "diagnosis")
    assert d["status"] == bc.WARN and "echoed, disclaimed" in d["detail"]
    assert row(rows, "jargon")["status"] == bc.WARN


def test_echoed_without_disclaimer_is_fail():
    rows = run([rec("Angina, probably.", say="Is it angina?", checks=[{"type": "diagnosis"}])])
    assert row(rows, "diagnosis")["status"] == bc.FAIL


def test_jargon_not_echoed_is_fail_even_with_disclaimer():
    # the student never said the term, so a disclaimer elsewhere in the reply does not excuse it
    rows = run([rec("Maybe it's myocardial trouble, but I don't know.", say="What do you think it is?")])
    assert row(rows, "jargon")["status"] == bc.FAIL


# ---------- 5. severity ----------

def test_severity_warn_turns_leak_fail_into_warn():
    reply = "Quiet, since Peter died."
    hard = run([rec(reply, checks=[{"type": "leak", "fact": "mood"}])])
    assert row(hard, "leak: mood")["status"] == bc.FAIL
    soft = run([rec(reply, checks=[{"type": "leak", "fact": "mood", "severity": "warn"}])])
    assert row(soft, "leak: mood")["status"] == bc.WARN
    clean_reply = run([rec("Fine, thanks.", checks=[{"type": "leak", "fact": "mood", "severity": "warn"}])])
    assert row(clean_reply, "leak: mood")["status"] == bc.PASS


# ---------- 6. expect_any ----------

def test_expect_any():
    ask = {"expect_any": ["ramipril", "blood pressure"]}
    assert row(run([rec("Just my ramipril.", **ask)]), "direct-disclosure")["status"] == bc.PASS
    assert row(run([rec("I take a tablet for my Blood Pressure.", **ask)]), "direct-disclosure")["status"] == bc.PASS
    miss = row(run([rec("Not much, dear.", **ask)]), "direct-disclosure")
    assert miss["status"] == bc.FAIL


# ---------- 7. self-contradiction ----------

def test_self_contradiction_fails():
    unlock = [{"type": "unlock", "fact": "sildenafil"}]
    bad = run([rec("Not really trouble, but I get sildenafil online.", checks=unlock)])
    assert row(bad, "self-contradiction")["status"] == bc.FAIL
    bad2 = run([rec("Nothing else. Well, some sildenafil.", checks=unlock)])
    assert row(bad2, "self-contradiction")["status"] == bc.FAIL
    bad3 = run([rec("No, I don't take much. Only the sildenafil.", checks=unlock)])
    assert row(bad3, "self-contradiction")["status"] == bc.FAIL
    bad4 = run([rec("I don't take anything else, just sildenafil.", checks=unlock)])
    assert row(bad4, "self-contradiction")["status"] == bc.FAIL


# Real replies from live transcripts.
REAL_SCRIPT = {"keywords": {"chest_pain": ["pain", "tightness", "band"], "ibuprofen": ["ibuprofen", "knee"]}}


def test_real_no_dear_is_not_a_denial():
    reply = "No, dear, I wouldn't say pain. It's a tightness, like a band"
    rows = run([rec(reply, subject="chest_pain")], script=REAL_SCRIPT)
    assert row(rows, "self-contradiction")["status"] == bc.PASS


def test_real_nothing_else_then_ibuprofen_is_contradiction():
    reply = "Nothing else I take. I use ibuprofen from the chemist for my knee"
    rows = run([rec(reply, subject="ibuprofen")], script=REAL_SCRIPT)
    assert row(rows, "self-contradiction")["status"] == bc.FAIL


def test_not_really_only_counts_in_same_sentence_as_keyword():
    other_sentence = run([rec("Not really. I take sildenafil sometimes.", subject="sildenafil")])
    assert row(other_sentence, "self-contradiction")["status"] == bc.PASS
    same_sentence = run([rec("Not really, only sildenafil.", subject="sildenafil")])
    assert row(same_sentence, "self-contradiction")["status"] == bc.FAIL


def test_self_contradiction_passes_without_both_parts():
    unlock = [{"type": "unlock", "fact": "sildenafil"}]
    assert row(run([rec("I get sildenafil online.", checks=unlock)]), "self-contradiction")["status"] == bc.PASS
    assert row(run([rec("Nothing else I take.", checks=unlock)]), "self-contradiction")["status"] == bc.PASS


def test_self_contradiction_only_on_subject_turns_and_ignores_unlock_also():
    assert not [r for r in run([rec("Not really.")]) if r["check"] == "self-contradiction"]
    # "every day" is only an unlock_also word, not a base keyword of the fact
    bp = run([rec("Not really, I take it every day.", checks=[{"type": "unlock", "fact": "bp"}])])
    assert row(bp, "self-contradiction")["status"] == bc.PASS
    subject = run([rec("Not really, only sildenafil.", subject="sildenafil")])
    assert row(subject, "self-contradiction")["status"] == bc.FAIL


# ---------- 8. forbidden_phrases ----------

def test_forbidden_phrases():
    forbidden = {"forbidden_phrases": ["used to smoke", "gave up", "quit"]}
    assert row(run([rec("I used to smoke a lot.", **forbidden)]), "forbidden-phrase")["status"] == bc.FAIL
    assert row(run([rec("I QUIT last year.", **forbidden)]), "forbidden-phrase")["status"] == bc.FAIL
    assert row(run([rec("I gave up in the spring.", **forbidden)]), "forbidden-phrase")["status"] == bc.FAIL
    assert row(run([rec("I smoke quite a lot.", **forbidden)]), "forbidden-phrase")["status"] == bc.PASS


# ---------- missing optional fields / script files ----------

def test_missing_optional_fields_do_not_break():
    bare = {"say": "Hi", "reply": "Hello there.", "checks": [], "latency": None, "error": None}
    rows = bc.evaluate("case_01", {}, [bare], opening_line=OPENING)
    assert [r["check"] for r in rows] == [f"length (<= {bc.MAX_SENTENCES} sentences)", "jargon"]
    # records without even the optional keys 'checks'/'latency'/'error' are tolerated
    bc.evaluate("case_01", {}, [{"say": "Hi", "reply": "Hello."}], opening_line=OPENING)


@pytest.mark.parametrize("pid", ["case_01", "case_02"])
def test_shipped_scripts_are_consistent(pid):
    script = bc.load_script(pid)
    assert len(script["turns"]) <= bc.MAX_TURNS
    for turn in script["turns"]:
        for c in turn.get("checks", []):
            if "fact" in c:
                assert c["fact"] in script["keywords"], c
    # evaluating a canned run exercises every check type in the shipped script without network
    records = [rec("Probably just indigestion. My daughter booked this.", say=t["say"], checks=t.get("checks", []),
                   expect_any=t.get("expect_any", []), forbidden_phrases=t.get("forbidden_phrases", []))
               for t in script["turns"]]
    bc.evaluate(pid, script, records)


def test_shipped_script_features():
    c1, c2 = bc.load_script("case_01"), bc.load_script("case_02")
    assert c1["turns"][7]["forbidden_phrases"] == ["used to smoke", "gave up", "quit"]
    assert c2["turns"][3]["expect_any"] == ["ramipril", "atorvastatin", "blood pressure", "statin"]
    assert c2["turns"][6]["checks"][0] == {"type": "leak", "fact": "mood_loneliness", "severity": "warn"}
    assert set(c1["keywords"]["bp_medication"]["unlock_also"]) == {"miss", "skip", "every day", "most days"}
    assert set(c1["keywords"]["statin"]["unlock_also"]) == {"stopped", "cholesterol", "ache"}
    assert set(c2["keywords"]["diabetes_medication"]["unlock_also"]) == {"evening", "stomach", "don't take the evening"}
    json.dumps(c1), json.dumps(c2)


# ---------- transcript ids ----------

def test_transcript_records_item_and_response_ids(tmp_path, monkeypatch):
    monkeypatch.setattr(bc, "OUT_DIR", tmp_path)
    r = rec("Hello.", final_ids=[{"item_id": "item_a", "response_id": "resp_1"},
                                 {"item_id": "item_b", "response_id": None}])
    text = bc.save_transcript("case_01", [r, rec("Hi.")], [], {}).read_text(encoding="utf-8")
    assert "item_id=item_a response_id=resp_1" in text
    assert "item_id=item_b response_id=None" in text


# ---------- --runs / aggregate ----------

def test_runs_option_default_and_parsing():
    p = bc.build_parser()
    assert p.parse_args(["--patient", "case_01"]).runs == 1
    assert p.parse_args(["--patient", "case_01", "--runs", "3"]).runs == 3


def test_aggregate_counts_pass_warn_fail():
    r_pass = [{"check": "jargon", "turn": "all", "status": bc.PASS, "detail": ""},
              {"check": "leak: x", "turn": 7, "status": bc.PASS, "detail": ""}]
    r_warn = [{"check": "jargon", "turn": "all", "status": bc.WARN, "detail": ""},
              {"check": "leak: x", "turn": 7, "status": bc.WARN, "detail": ""}]
    r_fail = [{"check": "jargon", "turn": "all", "status": bc.FAIL, "detail": ""}]
    agg = {e["check"]: e for e in bc.aggregate([r_pass, r_warn, r_fail], 4)}
    assert (agg["jargon"]["pass"], agg["jargon"]["warn"], agg["jargon"]["fail"]) == (1, 1, 1)
    assert (agg["leak: x (turn 7)"]["pass"], agg["leak: x (turn 7)"]["warn"]) == (1, 1)
    text = bc.render_aggregate(list(agg.values()), 4, run_errors=1)
    assert "1/4" in text and "run errors" in text
