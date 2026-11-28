"""CLI smoke test for WS /ws/session (text mode by default).

  python scripts/ws_smoke_test.py --patient case_01 --text "Hi, what brings you in?" --text "Since when?"
  python scripts/ws_smoke_test.py --patient case_01 --hold 20     # keep a session open (busy test)
"""
import argparse
import asyncio
import json
import sys
from urllib.parse import urlencode

from websockets.asyncio.client import connect

TURN_TIMEOUT = 45


async def recv(ws) -> dict:
    return json.loads(await ws.recv())


def show(msg: dict) -> None:
    t = msg["type"]
    if t == "transcript.delta" and msg["role"] == "patient":
        print(msg["text"], end="", flush=True)
    elif t == "transcript.final" and msg["role"] == "patient":
        print()
    elif t == "latency":
        perceived = ""
        if msg.get("ttfa_ms") is not None and msg.get("vad_silence_ms") is not None:
            perceived = f" perceived_ms={msg['ttfa_ms'] + msg['vad_silence_ms']}"
        print(f"[latency] turn={msg['turn']} ttfa_ms={msg['ttfa_ms']} ttft_ms={msg['ttft_ms']} "
              f"vad_silence_ms={msg.get('vad_silence_ms')}{perceived}")
    elif t == "error":
        print(f"[error] {msg['code']}: {msg['message']}")
    elif t == "session.ended":
        print(f"[session.ended] reason={msg['reason']} turns={msg['turns']} usage={json.dumps(msg['usage'])}")
    elif t == "speech.started":
        print("[speech.started]")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--patient", required=True)
    ap.add_argument("--text", action="append", default=[], help="student turn; repeat for several turns")
    ap.add_argument("--mode", default="text", choices=["text", "voice"])
    ap.add_argument("--url", default="ws://127.0.0.1:8000")
    ap.add_argument("--hold", type=float, default=0, help="seconds to keep the session open before ending")
    a = ap.parse_args()

    url = f"{a.url}/ws/session?{urlencode({'patient_id': a.patient, 'mode': a.mode})}"
    async with connect(url) as ws:
        first = await recv(ws)
        if first["type"] != "session.ready":
            show(first)
            return 1
        card = first["patient_public"]
        print(f"[session.ready] mode={first.get('mode')} patient={card['display_name']}, {card['age']}, "
              f"{card['presenting_complaint']}")
        for text in a.text:
            print(f"\n> student: {text}\n< patient: ", end="", flush=True)
            await ws.send(json.dumps({"type": "text.send", "text": text}))
            while True:
                msg = await asyncio.wait_for(recv(ws), TURN_TIMEOUT)
                show(msg)
                if msg["type"] in ("latency", "session.ended"):
                    break
            if msg["type"] == "session.ended":
                return 1
        if a.hold:
            print(f"[holding session for {a.hold:.0f}s]")
            await asyncio.sleep(a.hold)
        await ws.send(json.dumps({"type": "session.end"}))
        while True:
            msg = await asyncio.wait_for(recv(ws), TURN_TIMEOUT)
            show(msg)
            if msg["type"] == "session.ended":
                return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
