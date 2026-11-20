"""Heckle & Hint — backend.

Tier 1: core quiz loop.  Tier 2: comedy layer (write-ins + votes, laugh meter,
heckles, style points / roast cards / spotlight, bits & stars, sound board,
question editor, finale with wager + awards + podium, follow card, set report).

Design notes
- One MongoDB document per room. Every write happens inside a per-room
  asyncio lock (read -> change -> save), and bumps `version`.
- No background workers: timers and the demo crowd are applied "lazily" by
  `tick()` on every request. Screens poll every 1.5 s, so this is plenty.
- Role filtering lives in the `view_*` functions. Players and the big screen
  never get the correct answer, host notes or unapproved player text.
- Laugh points live in a ledger ({entry_id: points}); totals are recomputed
  from it, so Undo / Back / retries can never double-count.
"""
import asyncio
import copy
import hashlib
import math
import os
import random
import re
import secrets
import time
import unicodedata
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import live
from .filters import clean_text
from .seed import DEMO_TEAMS, FINALE_QUESTION, SEED_QUESTIONS

MAX_TEAMS = 30
NAME_MAX, TEXT_MAX, HECKLE_MAX = 30, 80, 100
TEXT_COOLDOWN_MS = 8000
REACT_PER_SEC = 4
STYLE_POINTS, HECKLE_POINTS, WI_POINTS, WI_WIN_POINTS = 200, 100, 100, 300
MAX_APPROVED = 6
VOTE_MS = 20000
EFFECT_MS = {"style": 4000, "roast": 8000, "spotlight": 15000, "heckle": 8000, "sfx": 3000}
SFX = ("rimshot", "trombone", "airhorn", "drumroll", "ding", "buzz")
WAGER_STEPS = (0, 25, 50, 75, 100)
CODE_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"  # no I, no O
ROAST_LEVELS = ("off", "mild", "spicy")
TIMED_PHASES = ("question_open", "vote")
QUESTION_PHASES = ("question_open", "question_locked", "vote", "reveal", "riff", "scoreboard")
REVEALED_PHASES = ("reveal", "riff", "scoreboard")
VIRAL_PHASES = ("viral_vote", "viral_riff", "viral_rate", "viral_result")
VIRAL_MS = {"viral_vote": 15000, "viral_riff": 60000, "viral_rate": 15000}
VIRAL_FROM = ("lobby", "scoreboard")

app = FastAPI(title="Heckle & Hint")


def now_ms() -> int:  # tests monkeypatch this to control time
    return int(time.time() * 1000)


def round_half_up(x: float) -> int:
    return int(math.floor(x + 0.5))


def score_for(ms_taken: int, limit_ms: int, streak: int) -> int:
    """Correct = round(1000 × (1 − (ms/limit)/2)) + min(100 × streak, 500)."""
    base = round_half_up(1000 * (1 - (ms_taken / limit_ms) / 2))
    return base + min(100 * streak, 500)


# ---------------------------------------------------------------- database
_db = None
DB_MODE = "unknown"


async def get_db():
    """Real MongoDB if MONGO_URL is set and reachable, else in-memory Mongo."""
    global _db, DB_MODE
    if _db is not None:
        return _db
    url = os.environ.get("MONGO_URL")
    if url:
        try:
            from motor.motor_asyncio import AsyncIOMotorClient

            client = AsyncIOMotorClient(url, serverSelectionTimeoutMS=2500)
            await client.admin.command("ping")
            _db, DB_MODE = client[os.environ.get("MONGO_DB", "heckle_hint")], "mongodb"
            return _db
        except Exception as exc:  # silent fallback, but log it
            print(f"[heckle] MongoDB unreachable ({exc!r}); using in-memory store")
    from mongomock_motor import AsyncMongoMockClient

    _db, DB_MODE = AsyncMongoMockClient()["heckle_hint"], "memory"
    return _db


_locks: dict[str, asyncio.Lock] = {}
_last_text_at: dict[str, int] = {}  # device -> last time it submitted player text
_react_hist: dict[str, list] = {}  # device -> timestamps of accepted reactions (last second)


def room_lock(code: str) -> asyncio.Lock:
    return _locks.setdefault(code, asyncio.Lock())


def text_rate_ok(device: str) -> bool:
    """One text submission per device per 8 s."""
    now = now_ms()
    last = _last_text_at.get(device)
    if last is not None and now - last < TEXT_COOLDOWN_MS:
        return False
    _last_text_at[device] = now
    return True


def react_allowance(device: str, wanted: int) -> int:
    """Max 4 reactions (laughs + groans) per rolling second per phone."""
    now = now_ms()
    hist = [t for t in _react_hist.get(device, []) if now - t < 1000]
    ok = max(0, min(wanted, REACT_PER_SEC - len(hist)))
    _react_hist[device] = hist + [now] * ok
    return ok


def fail(status: int, code: str):
    raise HTTPException(status_code=status, detail={"error": code})


ROOM_DEFAULTS = {
    "ledger": {}, "heckles": {}, "effects": [], "bits": [], "stars": [], "react_log": [],
    "wi_approved": {}, "wi_hidden": {}, "wi_votes": {}, "wager": None, "seq": 0,
    "profile": {"host_name": "", "zalo": "", "facebook": "", "instagram": "", "tiktok": ""},
    "sim_laugh_at": 0,
    "drafts": [], "weekly": {"status": "idle", "origin": None},
    "viral": {"status": "idle", "cards": [], "origin": None},
}


def ensure_fields(room):
    for k, v in ROOM_DEFAULTS.items():
        room.setdefault(k, copy.deepcopy(v))
    return room


async def load_room(code: str) -> dict:
    db = await get_db()
    room = await db.rooms.find_one({"_id": code.upper()})
    if not room:
        fail(404, "room_not_found")
    return ensure_fields(room)


async def save_room(room: dict):
    db = await get_db()
    await db.rooms.replace_one({"_id": room["_id"]}, room, upsert=True)


def require_host(room: dict, key: str | None):
    if not key or not secrets.compare_digest(str(key), room["host_key"]):
        fail(403, "not_host")


def next_id(room, prefix):
    room["seq"] += 1
    return f"{prefix}{room['seq']}"


# ---------------------------------------------------------------- small helpers
def current_q(room):
    i = room["q_index"]
    return room["questions"][i] if 0 <= i < len(room["questions"]) else None


def final_index(room):
    qs = room["questions"]
    return len(qs) - 1 if qs and qs[-1].get("final") else None


def answers_for(room, i=None):
    i = room["q_index"] if i is None else i
    return room["answers"].setdefault(str(i), {})


def ledger_add(room, eid, tid, pts, kind, note=""):
    if eid in room["ledger"]:
        return False
    room["ledger"][eid] = {"team_id": tid, "pts": pts, "kind": kind, "note": note, "at": now_ms()}
    return True


def ledger_remove_prefix(room, prefix):
    for k in [k for k in room["ledger"] if k.startswith(prefix)]:
        del room["ledger"][k]


def norm_text(s: str) -> str:
    """Normalise for grouping duplicates: lower, no accents, '&'->and, no punctuation."""
    s = unicodedata.normalize("NFD", s.lower()).replace("đ", "d")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def gid_for(text: str) -> str:
    return hashlib.sha1(norm_text(text).encode()).hexdigest()[:8]


# ---------------------------------------------------------------- scoring
def wager_deltas(room):
    w, fi = room["wager"], final_index(room)
    if not w or fi is None or fi not in room["revealed"]:
        return {}
    ans = room["answers"].get(str(fi), {})
    out = {}
    for tid, pct in w["bets"].items():
        bet = round_half_up(max(0, w["totals"].get(tid, 0)) * pct / 100)
        if not bet:
            continue
        a = ans.get(tid)
        out[tid] = bet * (2 if tid in w["bottom"] else 1) if (a and a["correct"]) else -bet
    return out


def recompute_scores(room):
    """Brain = correct answers on revealed quiz questions (+ finale wager).
    Laugh = sum of the laugh ledger. Streak = consecutive correct quiz answers."""
    for t in room["teams"].values():
        t["brain"], t["streak"], t["laugh"] = 0, 0, 0
    for i in sorted(room["revealed"]):
        q = room["questions"][i]
        if q["type"] != "quiz":
            continue
        ans = room["answers"].get(str(i), {})
        for tid, t in room["teams"].items():
            a = ans.get(tid)
            if a and a["correct"]:
                t["brain"] += a["points"]
                t["streak"] += 1
            else:
                t["streak"] = 0
    for tid, d in wager_deltas(room).items():
        if tid in room["teams"]:
            room["teams"][tid]["brain"] += d
    for e in room["ledger"].values():
        if e["team_id"] in room["teams"]:
            room["teams"][e["team_id"]]["laugh"] += e["pts"]


def ranking(room):
    teams = list(room["teams"].values())
    totals = {t["id"]: t["brain"] + t["laugh"] for t in teams}
    ordered = sorted(teams, key=lambda t: (-totals[t["id"]], t["n"]))
    ranks = {t["id"]: 1 + sum(1 for v in totals.values() if v > totals[t["id"]]) for t in teams}
    return ordered, ranks


# ---------------------------------------------------------------- answers, write-ins, votes
def record_answer(room, tid, choice, at, text=None, mod=None):
    ans = answers_for(room)
    if tid in ans:
        return False  # first answer wins -> idempotent
    q = current_q(room)
    limit = q["time_limit"] * 1000
    ms = max(0, min(limit, at - room["q_started_at"]))
    if q["type"] == "writein":
        c = mod or clean_text(text or "", TEXT_MAX)
        ans[tid] = {"choice": None, "text": c["text"], "flagged": c["flagged"], "gid": gid_for(c["text"]),
                    "ms": ms, "correct": None, "points": 0, "at": at, "reason": c.get("mod_reason", "")}
        return True
    correct = None if q["type"] == "poll" else (choice == q["correct"])
    points = score_for(ms, limit, room["teams"][tid]["streak"]) if correct else 0
    ans[tid] = {"choice": choice, "ms": ms, "correct": correct, "points": points, "at": at}
    return True


def wi_groups(room, i=None):
    """Group write-in answers whose normalised text matches."""
    i = room["q_index"] if i is None else i
    key = str(i)
    approved, hidden = room["wi_approved"].get(key, []), room["wi_hidden"].get(key, [])
    votes = room["wi_votes"].get(key, {})
    groups = {}
    for tid, a in sorted(room["answers"].get(key, {}).items(), key=lambda kv: kv[1]["at"]):
        if not a.get("text"):
            continue
        g = groups.setdefault(a["gid"], {"gid": a["gid"], "text": a["text"], "teams": [], "flagged": False,
                                         "at": a["at"], "reason": ""})
        g["teams"].append(tid)
        g["flagged"] = g["flagged"] or a["flagged"]
        g["reason"] = g["reason"] or a.get("reason", "")
    for g in groups.values():
        g["approved"] = g["gid"] in approved
        g["hidden"] = g["gid"] in hidden
        g["votes"] = sum(1 for v in votes.values() if v == g["gid"])
    return sorted(groups.values(), key=lambda g: (-len(g["teams"]), g["at"]))


def approved_groups(room, i=None):
    return [g for g in wi_groups(room, i) if g["approved"] and not g["hidden"]]


def eligible_voters(room):
    groups = approved_groups(room)
    return [tid for tid in room["teams"] if any(tid not in g["teams"] for g in groups)]


def award_writein(room, i):
    ledger_remove_prefix(room, f"wi:{i}:")
    ledger_remove_prefix(room, f"wiw:{i}:")
    groups = approved_groups(room, i)
    for g in groups:
        for tid in g["teams"]:
            ledger_add(room, f"wi:{i}:{g['gid']}:{tid}", tid, WI_POINTS, "writein", g["text"])
    top = max((g["votes"] for g in groups), default=0)
    if top > 0:
        for g in groups:
            if g["votes"] == top:
                for tid in g["teams"]:
                    ledger_add(room, f"wiw:{i}:{g['gid']}:{tid}", tid, WI_WIN_POINTS, "writein_win", g["text"])


# ---------------------------------------------------------------- bits (riffs) + reactions
def active_bits(room, now):
    return [b for b in room["bits"] if b["start"] <= now and (b["end"] is None or now <= b["end"])]


def open_bit(room, kind, label, team_id=None, end=None, ref=None):
    if kind == "riff":  # re-entering the riff for the same question continues its bit
        for b in room["bits"]:
            if b["kind"] == "riff" and b["q_index"] == room["q_index"]:
                b["end"] = None
                return b
    b = {"id": next_id(room, "b"), "kind": kind, "label": label, "team_id": team_id, "ref": ref,
         "q_index": room["q_index"], "start": now_ms(), "end": end, "laughs": 0, "groans": 0,
         "teams_at": max(1, len(room["teams"]))}
    room["bits"].append(b)
    return b


def close_riff(room):
    for b in room["bits"]:
        if b["kind"] == "riff" and b["end"] is None:
            b["end"] = now_ms()


def add_reactions(room, laughs, groans, at=None):
    at = now_ms() if at is None else at
    room["react_log"].append([at, laughs, groans])
    room["react_log"] = [r for r in room["react_log"] if at - r[0] <= 5000][-200:]
    for b in active_bits(room, at):
        b["laughs"] += laughs
        b["groans"] += groans


def bit_score(b):
    return round(b["laughs"] / max(1, b["teams_at"]), 1)


def add_effect(room, kind, team_id=None, ref=None, **extra):
    now = now_ms()
    e = {"id": next_id(room, "e"), "kind": kind, "team_id": team_id, "ref": ref, "at": now,
         "until": now + EFFECT_MS[kind], **extra}
    room["effects"].append(e)
    return e


# ---------------------------------------------------------------- demo crowd
def demo_ids(room):
    return [tid for tid, t in room["teams"].items() if t["demo"]]


def schedule_sim(room):
    """Demo crowd: each demo team answers 2–6 s after open, ~60% correct."""
    room["sim_plan"] = {}
    if not room["sim_on"] or room["phase"] not in TIMED_PHASES:
        return
    q, now, ans = current_q(room), now_ms(), answers_for(room)
    if room["phase"] == "vote":
        groups = approved_groups(room)
        votes = room["wi_votes"].get(str(room["q_index"]), {})
        for tid in demo_ids(room):
            options = [g["gid"] for g in groups if tid not in g["teams"]]
            if options and tid not in votes:
                room["sim_plan"][tid] = {"at": now + random.randint(1000, 4000), "vote": random.choice(options)}
        return
    for tid in demo_ids(room):
        if tid in ans:
            continue
        plan = {"at": now + random.randint(2000, 6000), "choice": None}
        if q["type"] == "writein":
            if not q.get("demo_answers"):
                continue
            plan["text"] = random.choice(q["demo_answers"])
        elif q["type"] == "poll":
            plan["choice"] = random.randrange(4)
        elif random.random() < 0.6:
            plan["choice"] = q["correct"]
        else:
            plan["choice"] = random.choice([k for k in range(4) if k != q["correct"]])
        room["sim_plan"][tid] = plan


def sim_laughs(room, now) -> bool:
    """While a bit is running, demo teams laugh so the meter moves for judges."""
    if not room["sim_on"] or not demo_ids(room) or not active_bits(room, now):
        room["sim_laugh_at"] = now
        return False
    elapsed = min(3000, now - (room.get("sim_laugh_at") or now))
    if elapsed < 500:
        return False
    room["sim_laugh_at"] = now
    per_team = random.uniform(0.3, 2.6)  # laughs per second per demo team
    n = int(per_team * len(demo_ids(room)) * elapsed / 1000)
    if n <= 0:
        return False
    add_reactions(room, n, random.choice([0, 0, 1]), now)
    return True


# ---------------------------------------------------------------- phase machine
def open_question(room, i):
    room["q_index"] = i
    room["answers"][str(i)] = {}
    for k in ("wi_approved", "wi_hidden", "wi_votes"):
        room[k].pop(str(i), None)
    ledger_remove_prefix(room, f"wi:{i}:")
    ledger_remove_prefix(room, f"wiw:{i}:")
    room["revealed"] = [x for x in room["revealed"] if x != i]
    if room["questions"][i].get("final") and room["wager"]:
        room["wager"]["locked"] = True
    recompute_scores(room)
    q, now = room["questions"][i], now_ms()
    room.update(phase="question_open", q_started_at=now,
                phase_ends_at=now + q["time_limit"] * 1000,
                frozen=False, frozen_remaining=None)
    schedule_sim(room)


def lock_question(room):
    room.update(phase="question_locked", phase_ends_at=None, frozen=False,
                frozen_remaining=None, sim_plan={})


def start_vote(room):
    room["wi_votes"][str(room["q_index"])] = {}
    room.update(phase="vote", phase_ends_at=now_ms() + VOTE_MS, frozen=False, frozen_remaining=None)
    schedule_sim(room)


def do_reveal(room):
    i = room["q_index"]
    room.update(phase="reveal", phase_ends_at=None, frozen=False, sim_plan={})
    if i not in room["revealed"]:
        room["revealed"].append(i)
    if current_q(room)["type"] == "writein":
        award_writein(room, i)
    recompute_scores(room)


def start_wager(room):
    ordered, _ = ranking(room)
    bottom = [t["id"] for t in ordered[-3:]] if len(ordered) > 3 else []
    room["wager"] = {"totals": {t["id"]: t["brain"] + t["laugh"] for t in ordered}, "bottom": bottom,
                     "bets": {}, "locked": False}
    if room["sim_on"]:
        for tid in demo_ids(room):
            room["wager"]["bets"][tid] = random.choice(WAGER_STEPS)
    room.update(phase="wager", phase_ends_at=None, sim_plan={})


def go_next_question(room):
    nxt = room["q_index"] + 1
    if nxt < len(room["questions"]):
        if room["questions"][nxt].get("final") and room["phase"] != "wager":
            start_wager(room)
        else:
            open_question(room, nxt)
    else:
        room.update(phase="awards", phase_ends_at=None, sim_plan={})


# ---------------------------------------------------------------- Viral Drop (Tier 3)
def _viral_sim(room, kind):
    """Demo crowd votes / rates during a Viral Drop."""
    room["sim_plan"] = {}
    if not room["sim_on"]:
        return
    now, n = now_ms(), len(room["viral"]["cards"])
    for tid in demo_ids(room):
        if kind == "vote":
            room["sim_plan"][tid] = {"at": now + random.randint(1500, 6000), "viral_vote": random.randrange(n)}
        else:
            room["sim_plan"][tid] = {"at": now + random.randint(1000, 5000), "viral_rate": random.choice([3, 4, 4, 5, 5])}


def start_viral(room):
    v = room["viral"]
    v.update(return_phase=room["phase"], votes={}, ratings={}, winner=None, bit_id=None, status="live")
    room.update(phase="viral_vote", phase_ends_at=now_ms() + VIRAL_MS["viral_vote"], frozen=False, frozen_remaining=None)
    _viral_sim(room, "vote")


def viral_counts(room):
    counts = [0] * len(room["viral"]["cards"])
    for idx in room["viral"].get("votes", {}).values():
        if 0 <= idx < len(counts):
            counts[idx] += 1
    return counts


def start_viral_riff(room):
    v = room["viral"]
    counts = viral_counts(room)
    v["winner"] = max(range(len(counts)), key=lambda k: (counts[k], -k)) if counts else 0
    card = v["cards"][v["winner"]]
    b = open_bit(room, "viral", card["title"])
    v["bit_id"] = b["id"]
    room.update(phase="viral_riff", phase_ends_at=now_ms() + VIRAL_MS["viral_riff"], frozen=False,
                frozen_remaining=None, sim_plan={})


def _viral_bit(room):
    return next((b for b in room["bits"] if b["id"] == room["viral"].get("bit_id")), None)


def start_viral_rate(room):
    b = _viral_bit(room)
    if b and b["end"] is None:
        b["end"] = now_ms()
    room.update(phase="viral_rate", phase_ends_at=now_ms() + VIRAL_MS["viral_rate"], frozen=False, frozen_remaining=None)
    _viral_sim(room, "rate")


def viral_rating(room):
    r = list(room["viral"].get("ratings", {}).values())
    return (round(sum(r) / len(r), 1) if r else None), len(r)


def finish_viral(room):
    avg, n = viral_rating(room)
    b = _viral_bit(room)
    if b:
        b.update(rating=avg, ratings=n)
    room.update(phase="viral_result", phase_ends_at=None, frozen=False, frozen_remaining=None, sim_plan={})


def end_viral(room):
    b = _viral_bit(room)
    if b and b["end"] is None:
        b["end"] = now_ms()
    v = room["viral"]
    back = v.get("return_phase") or "lobby"
    v["status"] = "used"
    room.update(phase=back, phase_ends_at=None, frozen=False, frozen_remaining=None, sim_plan={})


def tick_viral(room, now) -> bool:
    changed, p, v = False, room["phase"], room["viral"]
    for tid, plan in list(room.get("sim_plan", {}).items()):
        if plan["at"] > now:
            continue
        if "viral_vote" in plan and p == "viral_vote":
            v["votes"].setdefault(tid, plan["viral_vote"])
        if "viral_rate" in plan and p == "viral_rate":
            v["ratings"].setdefault(tid, plan["viral_rate"])
        del room["sim_plan"][tid]
        changed = True
    timed_out = not room["frozen"] and room["phase_ends_at"] and now >= room["phase_ends_at"]
    n = len(room["teams"])
    if p == "viral_vote" and (timed_out or (n and len(v["votes"]) >= n)):
        start_viral_riff(room)
        changed = True
    elif p == "viral_riff" and timed_out:
        start_viral_rate(room)
        changed = True
    elif p == "viral_rate" and (timed_out or (n and len(v["ratings"]) >= n)):
        finish_viral(room)
        changed = True
    return changed


def tick(room) -> bool:
    """Apply time-based changes: demo crowd, auto-lock, auto vote end, sim laughs."""
    changed, now = False, now_ms()
    room["effects"] = [e for e in room["effects"] if e["until"] > now - 10000]
    p = room["phase"]
    if p in TIMED_PHASES:
        for tid, plan in sorted(room.get("sim_plan", {}).items(), key=lambda kv: kv[1]["at"]):
            if plan["at"] > now:
                continue
            in_time = room["frozen"] or plan["at"] <= room["phase_ends_at"]
            if in_time and tid in room["teams"]:
                if p == "vote":
                    room["wi_votes"].setdefault(str(room["q_index"]), {}).setdefault(tid, plan["vote"])
                else:
                    record_answer(room, tid, plan["choice"], plan["at"], plan.get("text"))
            del room["sim_plan"][tid]
            changed = True
        timed_out = not room["frozen"] and now >= room["phase_ends_at"]
        if p == "question_open":
            n_teams = len(room["teams"])
            if timed_out or (n_teams and len(answers_for(room)) >= n_teams):
                lock_question(room)
                changed = True
        else:
            votes = room["wi_votes"].get(str(room["q_index"]), {})
            voters = eligible_voters(room)
            if timed_out or (voters and all(v in votes for v in voters)):
                do_reveal(room)
                changed = True
    elif p in VIRAL_PHASES:
        changed = tick_viral(room, now) or changed
    if sim_laughs(room, now):
        changed = True
    return changed


def new_room(code, host_key):
    room = {
        "_id": code, "host_key": host_key, "version": 1, "created_at": now_ms(),
        "phase": "lobby", "q_index": -1,
        "questions": copy.deepcopy(SEED_QUESTIONS) + [copy.deepcopy(FINALE_QUESTION)],
        "teams": {}, "answers": {}, "revealed": [], "q_started_at": None,
        "phase_ends_at": None, "frozen": False, "frozen_remaining": None,
        "sim_on": False, "sim_plan": {}, "blackout": False, "team_seq": 0,
    }
    return ensure_fields(room)


def make_team(room, device_id, name, emoji, fact, roast, mic, demo=False, name_mod=None, fact_mod=None):
    room["team_seq"] += 1
    tid = f"t{room['team_seq']}"
    name_c = name_mod or clean_text(name, NAME_MAX)
    fact_c = fact_mod or clean_text(fact, TEXT_MAX)
    t = {
        "id": tid, "n": room["team_seq"], "device_id": device_id, "demo": demo,
        "name": name_c["text"], "name_status": "pending" if name_c["flagged"] else "ok",
        "name_hidden": False,
        "fact": fact_c["text"] or None,
        "fact_status": None if not fact_c["text"] else ("flagged" if fact_c["flagged"] else "pending"),
        "fact_hidden": False,
        "emoji": emoji, "roast": roast, "mic": bool(mic),
        "brain": 0, "laugh": 0, "streak": 0, "joined_at": now_ms(), "last_text_at": now_ms(),
        "name_reason": name_c.get("mod_reason", ""), "fact_reason": fact_c.get("mod_reason", ""),
    }
    if demo and t["fact"]:
        t["fact_status"] = "approved"
    room["teams"][tid] = t
    return t


def team_by_device(room, device_id):
    for t in room["teams"].values():
        if t["device_id"] == device_id:
            return t
    return None


# ---------------------------------------------------------------- comedy analytics
def riff_fuel(room):
    """Joke prompts for the host once answers lock (multiple-choice questions)."""
    q = current_q(room)
    if not q or q["type"] == "writein" or room["phase"] == "question_open":
        return []
    ans = answers_for(room)
    if not ans:
        return []
    by = [[], [], [], []]
    for tid, a in sorted(ans.items(), key=lambda kv: kv[1]["ms"]):
        if a.get("choice") is not None:
            by[a["choice"]].append(tid)
    counts = [len(x) for x in by]
    total = sum(counts)
    chips = []
    order = sorted(range(4), key=lambda k: -counts[k])
    top = order[0]
    if counts[top] >= 2:
        chips.append({"kind": "popular", "option": top, "count": counts[top], "teams": by[top]})
    if total >= 3:
        for k in range(4):
            if counts[k] == 1 and len([c for c in chips if c["kind"] == "lone_wolf"]) < 2:
                chips.append({"kind": "lone_wolf", "option": k, "teams": by[k]})
    a, b = order[0], order[1]
    if counts[a] >= 2 and counts[b] >= 2 and counts[a] - counts[b] <= 1:
        chips.append({"kind": "split", "options": [a, b], "counts": [counts[a], counts[b]]})
    if q["type"] == "quiz":
        wrong = [k for k in range(4) if k != q["correct"]]
        cw = max(wrong, key=lambda k: counts[k])
        if counts[cw] >= 2:
            chips.append({"kind": "confidently_wrong", "option": cw, "count": counts[cw], "teams": by[cw]})
        wrongs = [(a_["ms"], tid, a_["choice"]) for tid, a_ in ans.items() if a_["correct"] is False]
        if wrongs:
            ms, tid, ch = min(wrongs)
            chips.append({"kind": "fastest_wrong", "teams": [tid], "ms": ms, "option": ch})
    ordered, _ = ranking(room)
    for x, y in zip(ordered, ordered[1:]):
        ax, ay = ans.get(x["id"]), ans.get(y["id"])
        gap = (x["brain"] + x["laugh"]) - (y["brain"] + y["laugh"])
        if ax and ay and gap <= 300 and ax["choice"] != ay["choice"]:
            chips.append({"kind": "rivals", "teams": [x["id"], y["id"]], "gap": gap,
                          "options": [ax["choice"], ay["choice"]]})
            break
    return chips


def heckle_bit(room, hid):
    return next((b for b in room["bits"] if b["kind"] == "heckle" and b["ref"] == hid), None)


def best_heckle(room):
    shown = [h for h in room["heckles"].values() if h["status"] == "shown"]
    if not shown:
        return None
    return max(shown, key=lambda h: ((heckle_bit(room, h["id"]) or {}).get("laughs", 0), h["shown_at"] or 0))


def funniest_answer(room):
    best = None
    for i in room["revealed"]:
        if room["questions"][i]["type"] != "writein":
            continue
        for g in approved_groups(room, i):
            if g["votes"] > 0 and (best is None or g["votes"] >= best["votes"]):
                best = {**g, "q_index": i}
    return best


def compute_awards(room):
    teams = list(room["teams"].values())
    if not teams:
        return []
    out = []
    champ = max(teams, key=lambda t: (t["brain"], -t["n"]))
    out.append({"key": "champion", "team_id": champ["id"], "value": champ["brain"]})
    funny = max(teams, key=lambda t: (t["laugh"], -t["n"]))
    if funny["laugh"] > 0:
        out.append({"key": "funniest", "team_id": funny["id"], "value": funny["laugh"]})
    wrong_score = {}
    for i in room["revealed"]:
        q = room["questions"][i]
        if q["type"] != "quiz":
            continue
        for tid, a in room["answers"].get(str(i), {}).items():
            if a["correct"] is False and tid in room["teams"]:
                fast = a["ms"] <= q["time_limit"] * 500  # wrong in the first half of the clock
                wrong_score[tid] = wrong_score.get(tid, 0) + (2 if fast else 1)
    if wrong_score:
        tid = max(wrong_score, key=lambda k: (wrong_score[k], -room["teams"][k]["n"]))
        out.append({"key": "confidently_wrong", "team_id": tid, "value": wrong_score[tid]})
    h = best_heckle(room)
    if h and h["team_id"] in room["teams"]:
        out.append({"key": "best_heckle", "team_id": h["team_id"], "text": h["text"],
                    "value": (heckle_bit(room, h["id"]) or {}).get("laughs", 0)})
    return out


# ---------------------------------------------------------------- views (role filtering)
def public_team(room, t, ranks, for_screen):
    blackout = for_screen and room["blackout"]
    show_name = t["name_status"] == "ok" and not t["name_hidden"] and not blackout
    show_fact = t["fact_status"] == "approved" and not t["fact_hidden"] and not blackout
    return {
        "id": t["id"], "n": t["n"], "emoji": t["emoji"],
        "name": t["name"] if show_name else None,  # None -> client shows "Team n"
        "fact": t["fact"] if show_fact else None,
        "brain": t["brain"], "laugh": t["laugh"], "total": t["brain"] + t["laugh"],
        "rank": ranks.get(t["id"]),
    }


def pub(room, tid, ranks, for_screen=True):
    t = room["teams"].get(tid)
    return public_team(room, t, ranks, for_screen) if t else None


def public_question(room, for_screen):
    q = current_q(room)
    if not q or room["phase"] not in QUESTION_PHASES:
        return None
    out = {"i": room["q_index"], "type": q["type"], "text": q["text"],
           "options": q["options"], "time_limit": q["time_limit"], "final": bool(q.get("final"))}
    blackout = for_screen and room["blackout"]
    if q["type"] == "writein" and room["phase"] in ("vote",) + REVEALED_PHASES:
        groups = approved_groups(room)
        top = max((g["votes"] for g in groups), default=0)
        out["choices"] = [{"gid": g["gid"], "text": None if blackout else g["text"],
                           **({"votes": g["votes"], "win": top > 0 and g["votes"] == top}
                              if room["phase"] in REVEALED_PHASES else {})} for g in groups]
    if q["type"] != "writein" and room["phase"] in REVEALED_PHASES:
        counts = [0, 0, 0, 0]
        for a in answers_for(room).values():
            if a.get("choice") is not None:
                counts[a["choice"]] += 1
        out["correct"] = q["correct"]
        out["counts"] = counts
        if q.get("source"):
            out["source"] = q["source"]
    return out


def public_effects(room, ranks, for_screen, team_id=None):
    now, out = now_ms(), []
    for e in room["effects"]:
        if e["until"] < now - (2000 if e["kind"] == "sfx" else 0):
            continue
        if not for_screen and (e["kind"] in ("sfx", "heckle") or e.get("team_id") != team_id):
            continue
        x = {"id": e["id"], "kind": e["kind"], "at": e["at"], "until": e["until"]}
        if e["kind"] == "sfx":
            x["name"] = e["name"]
        if e["kind"] == "style":
            x["points"] = STYLE_POINTS
        if e.get("team_id"):
            x["team"] = pub(room, e["team_id"], ranks, for_screen)
        if e["kind"] == "heckle":
            h = room["heckles"].get(e["ref"])
            if not h or h["status"] != "shown":
                continue
            x["text"] = None if room["blackout"] else h["text"]
        out.append(x)
    return out


def public_awards(room, ranks, for_screen):
    if room["phase"] not in ("awards", "podium", "ended"):
        return None
    out = []
    for a in compute_awards(room):
        x = {"key": a["key"], "team": pub(room, a["team_id"], ranks, for_screen), "value": a["value"]}
        if a["key"] == "best_heckle":
            x["text"] = None if (for_screen and room["blackout"]) else a["text"]
        out.append(x)
    return out


def public_viral(room, host=False):
    v, p = room["viral"], room["phase"]
    if host:
        out = {k: v.get(k) for k in ("status", "origin", "winner", "return_phase")}
        out["cards"] = v.get("cards", [])
        if p in VIRAL_PHASES:
            out["counts"] = viral_counts(room)
            out["rating"], out["rated"] = viral_rating(room)
        return out
    if p not in VIRAL_PHASES:
        return None
    out = {"cards": [{k: c.get(k) for k in ("title", "text", "credit", "url")} for c in v["cards"]],
           "winner": v.get("winner")}
    if p != "viral_vote":
        out["counts"] = viral_counts(room)
    if p == "viral_result":
        out["rating"], out["rated"] = viral_rating(room)
    return out


def public_profile(room):
    return {k: v for k, v in room["profile"].items() if v}


def base_view(room):
    in_q = room["phase"] in QUESTION_PHASES
    q = current_q(room)
    answered = len(answers_for(room)) if in_q else 0
    if room["phase"] == "vote":
        answered = len(room["wi_votes"].get(str(room["q_index"]), {}))
    if room["phase"] == "viral_vote":
        answered = len(room["viral"].get("votes", {}))
    if room["phase"] in ("viral_rate", "viral_result"):
        answered = len(room["viral"].get("ratings", {}))
    return {
        "code": room["_id"], "version": room["version"], "server_now": now_ms(),
        "phase": room["phase"], "q_index": room["q_index"],
        "q_total": len(room["questions"]),
        "is_final": bool(q and q.get("final")) and in_q,
        "phase_ends_at": room["phase_ends_at"], "frozen": room["frozen"],
        "frozen_remaining": room["frozen_remaining"],
        "team_count": len(room["teams"]),
        "answered_count": answered,
        "voters_count": len(eligible_voters(room)) if room["phase"] == "vote" else 0,
    }


def view_screen(room):
    ordered, ranks = ranking(room)
    v = base_view(room)
    w = room["wager"]
    v.update(role="screen", blackout=room["blackout"], question=public_question(room, True),
             teams=[public_team(room, t, ranks, True) for t in sorted(room["teams"].values(), key=lambda t: t["n"])],
             top=[public_team(room, t, ranks, True) for t in ordered[:5]],
             react_log=room["react_log"], effects=public_effects(room, ranks, True),
             awards=public_awards(room, ranks, True),
             wager=({"bottom": [pub(room, tid, ranks) for tid in w["bottom"]], "placed": len(w["bets"])}
                    if w and room["phase"] == "wager" else None),
             profile=public_profile(room) if room["phase"] == "ended" else None,
             viral=public_viral(room))
    return v


def view_player(room, device_id):
    ordered, ranks = ranking(room)
    v = base_view(room)
    me = team_by_device(room, device_id) if device_id else None
    v.update(role="player", question=public_question(room, False), me=None, my_answer=None)
    if not me:
        return v
    v["me"] = {
        "id": me["id"], "n": me["n"], "name": me["name"], "name_status": me["name_status"],
        "emoji": me["emoji"], "roast": me["roast"], "mic": me["mic"],
        "brain": me["brain"], "laugh": me["laugh"], "total": me["brain"] + me["laugh"],
        "streak": me["streak"], "rank": ranks[me["id"]],
    }
    q = current_q(room)
    if room["phase"] in QUESTION_PHASES:
        a = answers_for(room).get(me["id"])
        if a:
            mine = {"choice": a["choice"]} if q["type"] != "writein" else {"text": a["text"], "gid": a["gid"]}
            if room["phase"] in REVEALED_PHASES and q["type"] != "writein":  # correctness only after reveal
                mine.update(correct=a["correct"], points=a["points"])
            v["my_answer"] = mine
        if room["phase"] == "vote" or (q["type"] == "writein" and room["phase"] in REVEALED_PHASES):
            v["my_vote"] = room["wi_votes"].get(str(room["q_index"]), {}).get(me["id"])
            v["my_groups"] = [g["gid"] for g in approved_groups(room) if me["id"] in g["teams"]]
            if room["phase"] in REVEALED_PHASES:
                i = room["q_index"]
                v["my_laugh_won"] = sum(e["pts"] for k, e in room["ledger"].items() if e["team_id"] == me["id"]
                                        and (k.startswith(f"wi:{i}:") or k.startswith(f"wiw:{i}:")))
        if q.get("final") and room["phase"] in REVEALED_PHASES:
            v["wager_delta"] = wager_deltas(room).get(me["id"], 0)
    w = room["wager"]
    if w and (room["phase"] == "wager" or (q and q.get("final") and room["phase"] in QUESTION_PHASES)):
        pct = w["bets"].get(me["id"], 0)
        v["wager"] = {"pct": pct, "bottom": me["id"] in w["bottom"], "locked": w["locked"],
                      "bet": round_half_up(max(0, w["totals"].get(me["id"], 0)) * pct / 100),
                      "base": w["totals"].get(me["id"], 0)}
    v["effects"] = public_effects(room, ranks, False, me["id"])
    v["awards"] = public_awards(room, ranks, False)
    v["viral"] = public_viral(room)
    if v["viral"] is not None:
        v["viral"]["my_vote"] = room["viral"].get("votes", {}).get(me["id"])
        v["viral"]["my_rating"] = room["viral"].get("ratings", {}).get(me["id"])
    if room["phase"] == "ended":
        v["profile"] = public_profile(room)
    return v


def view_host(room):
    ordered, ranks = ranking(room)
    v = base_view(room)
    q = current_q(room)
    teams = []
    for t in sorted(room["teams"].values(), key=lambda t: t["n"]):
        x = {k: t[k] for k in ("id", "n", "name", "name_status", "name_hidden", "fact", "fact_status",
                               "fact_hidden", "emoji", "roast", "mic", "demo", "brain", "laugh", "streak")}
        x.update(name_reason=t.get("name_reason", ""), fact_reason=t.get("fact_reason", ""))
        x.update(total=t["brain"] + t["laugh"], rank=ranks[t["id"]])
        teams.append(x)
    nxt = room["questions"][room["q_index"] + 1] if room["q_index"] + 1 < len(room["questions"]) else None
    now = now_ms()
    heckles = sorted(room["heckles"].values(), key=lambda h: -h["at"])[:60]
    v.update(
        role="host", blackout=room["blackout"], sim_on=room["sim_on"],
        demo_loaded=any(t["demo"] for t in room["teams"].values()),
        question=({"i": room["q_index"], **q} if q and room["phase"] in QUESTION_PHASES else None),
        next_question=({"i": room["q_index"] + 1, "type": nxt["type"], "text": nxt["text"],
                        "final": bool(nxt.get("final"))} if nxt else None),
        answers=answers_for(room) if room["phase"] in QUESTION_PHASES else {},
        teams=teams, leaderboard=[t["id"] for t in ordered], db_mode=DB_MODE,
        riff_fuel=riff_fuel(room) if room["phase"] in QUESTION_PHASES else [],
        writeins=wi_groups(room) if q and q["type"] == "writein" and room["phase"] in QUESTION_PHASES else [],
        votes=room["wi_votes"].get(str(room["q_index"]), {}),
        heckles=[{**h, "laughs": (heckle_bit(room, h["id"]) or {}).get("laughs", 0)} for h in heckles],
        effects=[e for e in room["effects"] if e["until"] > now],
        react_log=room["react_log"],
        active_bit=next((b["label"] for b in active_bits(room, now)), None),
        stars=room["stars"][-20:], profile=room["profile"], wager=room["wager"],
        awards=compute_awards(room) if room["phase"] in ("awards", "podium", "ended") else None,
        sfx=list(SFX),
        live=live.status(), weekly=room["weekly"], drafts=room["drafts"],
        viral=public_viral(room, host=True), viral_can_send=room["phase"] in VIRAL_FROM,
    )
    return v


def view_for(room, role, device_id):
    if role == "host":
        return view_host(room)
    if role == "screen":
        return view_screen(room)
    return view_player(room, device_id)


# ---------------------------------------------------------------- helpers
async def body_json(request: Request) -> dict:
    try:
        data = await request.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


async def mutate(code, fn):
    """Run fn(room) under the room lock; save + bump version if it changed."""
    code = code.upper()
    async with room_lock(code):
        room = await load_room(code)
        changed = tick(room)
        result = fn(room)
        if changed or result is not False:
            room["version"] += 1
            await save_room(room)
        return room


def player_team(room, device):
    t = team_by_device(room, device)
    if not t:
        fail(404, "not_joined")
    return t


# ---------------------------------------------------------------- routes: public + players
@app.get("/api/health")
async def health():
    await get_db()
    return {"ok": True, "db": DB_MODE}


@app.post("/api/rooms")
async def create_room():
    db = await get_db()
    for _ in range(50):
        code = "".join(random.choice(CODE_LETTERS) for _ in range(4))
        if not await db.rooms.find_one({"_id": code}, {"_id": 1}):
            break
    host_key = secrets.token_urlsafe(16)
    await save_room(new_room(code, host_key))
    return {"code": code, "host_key": host_key}


@app.get("/api/rooms/{code}/state")
async def get_state(code: str, role: str = "player", since: int | None = None,
                    device: str | None = None, x_host_key: str | None = Header(None), key: str | None = None):
    code = code.upper()
    if role not in ("host", "player", "screen"):
        role = "player"
    async with room_lock(code):
        room = await load_room(code)
        if role == "host":
            require_host(room, x_host_key or key)
        if tick(room):
            room["version"] += 1
            await save_room(room)
    if since is not None and since == room["version"]:
        return {"unchanged": True, "version": room["version"], "server_now": now_ms()}
    return view_for(room, role, device)


@app.post("/api/rooms/{code}/join")
async def join(code: str, request: Request):
    data = await body_json(request)
    device = str(data.get("device_id") or "")[:64]
    if len(device) < 8:
        fail(400, "bad_device")
    name = str(data.get("name") or "").strip()
    if not name:
        fail(400, "name_required")
    roast = data.get("roast") if data.get("roast") in ROAST_LEVELS else "mild"
    emoji = str(data.get("emoji") or "🍻")[:8]
    fact = str(data.get("fact") or "")
    out = {}
    name_mod, fact_mod = await asyncio.gather(live.moderate(name, NAME_MAX, "team name"),
                                              live.moderate(fact, TEXT_MAX, "fun fact"))

    def fn(room):
        existing = team_by_device(room, device)
        if existing:  # retry / refresh: same team back, no duplicate
            out["team"] = existing
            return False
        if len(room["teams"]) >= MAX_TEAMS:
            fail(409, "room_full")
        if not text_rate_ok(device):
            fail(429, "too_fast")
        out["team"] = make_team(room, device, name, emoji, fact, roast, data.get("mic"), name_mod=name_mod, fact_mod=fact_mod)
        recompute_scores(room)

    room = await mutate(code, fn)
    return {"team_id": out["team"]["id"], "state": view_player(room, device)}


@app.post("/api/rooms/{code}/answer")
async def answer(code: str, request: Request):
    data = await body_json(request)
    device = str(data.get("device_id") or "")
    choice, q_index = data.get("choice"), data.get("q_index")
    text_in = str(data.get("text") or "").strip()
    mod = await live.moderate(text_in, TEXT_MAX, "write-in answer") if text_in else None

    def fn(room):
        t = player_team(room, device)
        if q_index != room["q_index"]:
            fail(409, "question_moved_on")
        if answers_for(room).get(t["id"]):
            return False  # already answered: a retry, all good
        if room["phase"] != "question_open":
            fail(409, "answers_locked")
        q = current_q(room)
        if q["type"] == "writein":
            text = str(data.get("text") or "").strip()
            if not text:
                fail(400, "text_required")
            if not text_rate_ok(device):
                fail(429, "too_fast")
            record_answer(room, t["id"], None, now_ms(), text, mod=mod)
        else:
            if choice not in (0, 1, 2, 3):
                fail(400, "bad_choice")
            record_answer(room, t["id"], choice, now_ms())
        if len(answers_for(room)) >= len(room["teams"]):
            lock_question(room)

    room = await mutate(code, fn)
    return view_player(room, device)


@app.post("/api/rooms/{code}/vote")
async def vote(code: str, request: Request):
    data = await body_json(request)
    device = str(data.get("device_id") or "")

    def fn(room):
        t = player_team(room, device)
        if data.get("q_index") != room["q_index"]:
            fail(409, "question_moved_on")
        votes = room["wi_votes"].setdefault(str(room["q_index"]), {})
        if t["id"] in votes:
            return False
        if room["phase"] != "vote":
            fail(409, "answers_locked")
        g = next((g for g in approved_groups(room) if g["gid"] == data.get("gid")), None)
        if not g:
            fail(400, "bad_choice")
        if t["id"] in g["teams"]:
            fail(409, "own_answer")
        votes[t["id"]] = g["gid"]
        voters = eligible_voters(room)
        if voters and all(v in votes for v in voters):
            do_reveal(room)

    room = await mutate(code, fn)
    return view_player(room, device)


@app.post("/api/rooms/{code}/wager")
async def wager(code: str, request: Request):
    data = await body_json(request)
    device = str(data.get("device_id") or "")
    pct = data.get("pct")

    def fn(room):
        t = player_team(room, device)
        w = room["wager"]
        if room["phase"] != "wager" or not w or w["locked"]:
            fail(409, "answers_locked")
        if pct not in WAGER_STEPS:
            fail(400, "bad_choice")
        if w["bets"].get(t["id"]) == pct:
            return False
        w["bets"][t["id"]] = pct

    room = await mutate(code, fn)
    return view_player(room, device)


@app.post("/api/rooms/{code}/viral_vote")
async def viral_vote(code: str, request: Request):
    data = await body_json(request)
    device = str(data.get("device_id") or "")

    def fn(room):
        t = player_team(room, device)
        v = room["viral"]
        if t["id"] in v.get("votes", {}):
            return False
        if room["phase"] != "viral_vote":
            fail(409, "answers_locked")
        idx = data.get("idx")
        if idx not in range(len(v["cards"])):
            fail(400, "bad_choice")
        v["votes"][t["id"]] = idx
        if len(v["votes"]) >= len(room["teams"]):
            start_viral_riff(room)

    room = await mutate(code, fn)
    return view_player(room, device)


@app.post("/api/rooms/{code}/viral_rate")
async def viral_rate(code: str, request: Request):
    data = await body_json(request)
    device = str(data.get("device_id") or "")

    def fn(room):
        t = player_team(room, device)
        v = room["viral"]
        if t["id"] in v.get("ratings", {}):
            return False
        if room["phase"] != "viral_rate":
            fail(409, "answers_locked")
        stars = data.get("stars")
        if stars not in (1, 2, 3, 4, 5):
            fail(400, "bad_choice")
        v["ratings"][t["id"]] = stars
        if len(v["ratings"]) >= len(room["teams"]):
            finish_viral(room)

    room = await mutate(code, fn)
    return view_player(room, device)


@app.post("/api/rooms/{code}/react")
async def react(code: str, request: Request):
    """LAUGH / GROAN from a phone. Max 4 per second per phone (laughs + groans)."""
    data = await body_json(request)
    device = str(data.get("device_id") or "")
    try:
        want_l = max(0, min(20, int(data.get("laughs") or 0)))
        want_g = max(0, min(20, int(data.get("groans") or 0)))
    except (TypeError, ValueError):
        fail(400, "bad_request")
    out = {"laughs": 0, "groans": 0}

    def fn(room):
        player_team(room, device)
        ok_l = react_allowance(device, want_l)
        ok_g = react_allowance(device, want_g)
        out.update(laughs=ok_l, groans=ok_g)
        if not ok_l and not ok_g:
            return False
        add_reactions(room, ok_l, ok_g)

    await mutate(code, fn)
    return {"accepted": out}


@app.post("/api/rooms/{code}/heckle")
async def heckle(code: str, request: Request):
    data = await body_json(request)
    device = str(data.get("device_id") or "")
    client_id = re.sub(r"[^A-Za-z0-9_-]", "", str(data.get("id") or ""))[:40]
    text = str(data.get("text") or "").strip()
    mod = await live.moderate(text, HECKLE_MAX, "heckle") if text else None

    def fn(room):
        t = player_team(room, device)
        hid = f"h-{client_id}" if client_id else None
        if hid and hid in room["heckles"]:
            return False  # retry of the same heckle
        if not text:
            fail(400, "text_required")
        if not text_rate_ok(device):
            fail(429, "too_fast")
        c = mod or clean_text(text, HECKLE_MAX)
        hid = hid or next_id(room, "h-")
        room["heckles"][hid] = {"id": hid, "team_id": t["id"], "text": c["text"], "flagged": c["flagged"],
                                "reason": c.get("mod_reason", ""),
                                "status": "pending", "at": now_ms(), "shown_at": None, "q_index": room["q_index"]}
        if len(room["heckles"]) > 300:  # keep the doc small: drop the oldest non-shown ones
            for old in sorted(room["heckles"].values(), key=lambda h: h["at"])[:50]:
                if old["status"] != "shown":
                    del room["heckles"][old["id"]]

    await mutate(code, fn)
    return {"ok": True}


@app.get("/api/rooms/{code}/recap")
async def recap(code: str):
    room = await load_room(code)
    ordered, ranks = ranking(room)
    h = best_heckle(room)
    f = funniest_answer(room)
    awards = []
    if room["phase"] in ("awards", "podium", "ended"):
        for a in compute_awards(room):
            x = {"key": a["key"], "value": a["value"], "team": pub(room, a["team_id"], ranks, False)}
            if "text" in a:
                x["text"] = a["text"]
            awards.append(x)
    return {
        "code": room["_id"], "phase": room["phase"],
        "top": [public_team(room, t, ranks, False) for t in ordered[:3] if t["brain"] + t["laugh"] > 0],
        "best_heckle": ({"text": h["text"], "team": pub(room, h["team_id"], ranks, False)} if h else None),
        "funniest_answer": ({"text": f["text"], "votes": f["votes"],
                             "teams": [pub(room, tid, ranks, False) for tid in f["teams"]]} if f else None),
        "awards": awards, "profile": public_profile(room),
    }


# ---------------------------------------------------------------- host actions
HOST_ACTIONS = {}


def host_action(name):
    def deco(fn):
        HOST_ACTIONS[name] = fn
        return fn
    return deco


def get_team(room, data):
    t = room["teams"].get(data.get("team_id"))
    if not t:
        fail(400, "bad_request")
    return t


@host_action("next")
def act_next(room, data, out):
    p = room["phase"]
    if p == "lobby":
        go_next_question(room)
    elif p == "question_open":
        lock_question(room)
    elif p == "question_locked":
        if current_q(room)["type"] == "writein" and approved_groups(room):
            start_vote(room)
        else:
            do_reveal(room)
    elif p == "vote":
        do_reveal(room)
    elif p == "reveal":
        room["phase"] = "riff"
        open_bit(room, "riff", current_q(room)["text"])
    elif p == "riff":
        close_riff(room)
        room["phase"] = "scoreboard"
    elif p == "scoreboard":
        go_next_question(room)
    elif p == "wager":
        open_question(room, room["q_index"] + 1)
    elif p == "awards":
        room["phase"] = "podium"
    elif p == "podium":
        room["phase"] = "ended"
    elif p == "viral_vote":
        start_viral_riff(room)
    elif p == "viral_riff":
        start_viral_rate(room)
    elif p == "viral_rate":
        finish_viral(room)
    elif p == "viral_result":
        end_viral(room)
    else:
        return False


@host_action("back")
def act_back(room, data, out):
    p, i = room["phase"], room["q_index"]
    if p in VIRAL_PHASES:  # cancel the Viral Drop, go back where we were
        end_viral(room)
        return
    if p == "question_open":
        room["answers"][str(i)] = {}
        room["sim_plan"] = {}
        if current_q(room).get("final") and room["wager"]:
            room["wager"]["locked"] = False
            room.update(q_index=i - 1, phase="wager", phase_ends_at=None)
        elif i > 0:
            room.update(q_index=i - 1, phase="scoreboard", phase_ends_at=None)
        else:
            room.update(q_index=-1, phase="lobby", phase_ends_at=None)
    elif p == "question_locked":  # re-open with 10 s on the clock
        room.update(phase="question_open", phase_ends_at=now_ms() + 10000, frozen=False)
        schedule_sim(room)
    elif p == "vote":
        room["wi_votes"].pop(str(i), None)
        room.update(phase="question_locked", phase_ends_at=None, sim_plan={})
    elif p == "reveal":
        room["revealed"] = [x for x in room["revealed"] if x != i]
        ledger_remove_prefix(room, f"wi:{i}:")
        ledger_remove_prefix(room, f"wiw:{i}:")
        room["wi_votes"].pop(str(i), None)
        recompute_scores(room)
        room["phase"] = "question_locked"
    elif p == "riff":
        close_riff(room)
        room["phase"] = "reveal"
    elif p == "scoreboard":
        room["phase"] = "riff"
        open_bit(room, "riff", current_q(room)["text"])
    elif p == "wager":
        room["wager"] = None
        room["phase"] = "scoreboard" if i >= 0 else "lobby"
    elif p == "awards":
        room["phase"] = "scoreboard"
    elif p == "podium":
        room["phase"] = "awards"
    elif p == "ended":
        room["phase"] = "podium"
    else:
        return False


@host_action("skip")
def act_skip(room, data, out):
    p, i = room["phase"], room["q_index"]
    if p in VIRAL_PHASES:
        end_viral(room)
        return
    if p in ("question_open", "question_locked", "vote"):
        room["answers"][str(i)] = {}
        room["wi_votes"].pop(str(i), None)
        go_next_question(room)
    elif p in REVEALED_PHASES:
        close_riff(room)
        go_next_question(room)
    else:
        return False


@host_action("reset")
def act_reset(room, data, out):
    room.update(phase="lobby", q_index=-1, answers={}, revealed=[], q_started_at=None,
                phase_ends_at=None, frozen=False, frozen_remaining=None, sim_plan={},
                ledger={}, heckles={}, effects=[], bits=[], stars=[], react_log=[],
                wi_approved={}, wi_hidden={}, wi_votes={}, wager=None)
    room["viral"] = {"status": "ready" if room["viral"].get("cards") else "idle", "cards": room["viral"].get("cards", []),
                     "origin": room["viral"].get("origin")}
    recompute_scores(room)


@host_action("add_time")
def act_add_time(room, data, out):
    if room["phase"] not in TIMED_PHASES + tuple(VIRAL_MS):
        return False
    if room["frozen"]:
        room["frozen_remaining"] = (room["frozen_remaining"] or 0) + 10000
    else:
        room["phase_ends_at"] += 10000


@host_action("freeze")
def act_freeze(room, data, out):
    if room["phase"] not in TIMED_PHASES + tuple(VIRAL_MS):
        return False
    want = data.get("frozen", not room["frozen"])
    if want == room["frozen"]:
        return False  # idempotent
    now = now_ms()
    if want:
        room.update(frozen=True, frozen_remaining=max(0, room["phase_ends_at"] - now))
    else:
        room.update(frozen=False, phase_ends_at=now + (room["frozen_remaining"] or 0), frozen_remaining=None)


@host_action("demo_load")
def act_demo_load(room, data, out):
    if any(t["demo"] for t in room["teams"].values()):
        return False  # already loaded: idempotent
    for k, (name, emoji, fact, roast, mic) in enumerate(DEMO_TEAMS):
        if len(room["teams"]) >= MAX_TEAMS:
            break
        make_team(room, f"demo-{k}-{room['_id']}", name, emoji, fact, roast, mic, demo=True)
    recompute_scores(room)


@host_action("demo_clear")
def act_demo_clear(room, data, out):
    ids = demo_ids(room)
    if not ids:
        return False
    for tid in ids:
        del room["teams"][tid]
        for ans in room["answers"].values():
            ans.pop(tid, None)
        for votes in room["wi_votes"].values():
            votes.pop(tid, None)
    room["sim_plan"] = {}
    room["sim_on"] = False
    recompute_scores(room)


@host_action("demo_sim")
def act_demo_sim(room, data, out):
    want = bool(data.get("on", not room["sim_on"]))
    if want == room["sim_on"]:
        return False
    room["sim_on"] = want
    room["sim_laugh_at"] = now_ms()
    schedule_sim(room)


@host_action("blackout")
def act_blackout(room, data, out):
    want = bool(data.get("on", not room["blackout"]))
    if want == room["blackout"]:
        return False
    room["blackout"] = want


@host_action("mod")
def act_mod(room, data, out):
    t = get_team(room, data)
    field, op = data.get("field"), data.get("op")
    if field not in ("name", "fact"):
        fail(400, "bad_request")
    if op == "approve":
        t[f"{field}_status"] = "ok" if field == "name" else "approved"
        t[f"{field}_hidden"] = False
    elif op == "hide":
        t[f"{field}_hidden"] = True
    elif op == "show":
        t[f"{field}_hidden"] = False
    else:
        fail(400, "bad_request")


@host_action("wi_mod")
def act_wi_mod(room, data, out):
    q = current_q(room)
    if not q or q["type"] != "writein" or room["phase"] not in ("question_open", "question_locked"):
        fail(409, "too_late")
    key, gid, op = str(room["q_index"]), data.get("gid"), data.get("op")
    if gid not in {g["gid"] for g in wi_groups(room)}:
        fail(400, "bad_request")
    approved = room["wi_approved"].setdefault(key, [])
    hidden = room["wi_hidden"].setdefault(key, [])
    if op == "approve":
        if gid in approved:
            return False
        if len(approved) >= MAX_APPROVED:
            fail(409, "max_six")
        approved.append(gid)
        if gid in hidden:
            hidden.remove(gid)
    elif op == "unapprove":
        if gid not in approved:
            return False
        approved.remove(gid)
    elif op == "hide":
        if gid in approved:
            approved.remove(gid)
        if gid not in hidden:
            hidden.append(gid)
    elif op == "show":
        if gid in hidden:
            hidden.remove(gid)
    else:
        fail(400, "bad_request")


@host_action("heckle")
def act_heckle(room, data, out):
    h = room["heckles"].get(data.get("heckle_id"))
    if not h:
        fail(400, "bad_request")
    op, now = data.get("op"), now_ms()
    if op == "show":
        if h["status"] == "shown" and any(e["ref"] == h["id"] and e["until"] > now for e in room["effects"]):
            return False  # already on screen (retry)
        for e in room["effects"]:  # one heckle on screen at a time
            if e["kind"] == "heckle" and e["until"] > now:
                e["until"] = now
        h.update(status="shown", shown_at=now)
        e = add_effect(room, "heckle", h["team_id"], ref=h["id"])
        b = heckle_bit(room, h["id"])
        if b:
            b["end"] = e["until"]
        else:
            open_bit(room, "heckle", h["text"], h["team_id"], end=e["until"], ref=h["id"])
        ledger_add(room, f"heckle:{h['id']}", h["team_id"], HECKLE_POINTS, "heckle", h["text"])
    elif op == "hide":
        h["status"] = "hidden"
        for e in room["effects"]:
            if e["ref"] == h["id"]:
                e["until"] = min(e["until"], now)
        room["ledger"].pop(f"heckle:{h['id']}", None)
    else:
        fail(400, "bad_request")
    recompute_scores(room)


def action_eid(room, prefix, data):
    aid = re.sub(r"[^A-Za-z0-9_-]", "", str(data.get("action_id") or ""))[:40]
    return f"{prefix}:{aid}" if aid else f"{prefix}:{next_id(room, '')}"


@host_action("style")
def act_style(room, data, out):
    t = get_team(room, data)
    eid = action_eid(room, "style", data)
    out["created"] = eid
    if not ledger_add(room, eid, t["id"], STYLE_POINTS, "style"):
        return False
    add_effect(room, "style", t["id"], ref=eid)
    recompute_scores(room)


@host_action("undo")
def act_undo(room, data, out):
    eid = str(data.get("entry_id") or "")
    if not eid.startswith("style:") or eid not in room["ledger"]:
        return False
    del room["ledger"][eid]
    for e in room["effects"]:
        if e["ref"] == eid:
            e["until"] = min(e["until"], now_ms())
    recompute_scores(room)


@host_action("roast")
def act_roast(room, data, out):
    t = get_team(room, data)
    if t["roast"] == "off":
        fail(409, "roast_off")
    eid = action_eid(room, "roast", data)
    if any(e["ref"] == eid for e in room["effects"]):
        return False
    e = add_effect(room, "roast", t["id"], ref=eid)
    open_bit(room, "roast", t["name"], t["id"], end=e["until"], ref=eid)


@host_action("spotlight")
def act_spotlight(room, data, out):
    t = get_team(room, data)
    if not t["mic"]:
        fail(409, "not_mic_ready")
    eid = action_eid(room, "spot", data)
    if any(e["ref"] == eid for e in room["effects"]):
        return False
    e = add_effect(room, "spotlight", t["id"], ref=eid)
    open_bit(room, "spotlight", t["name"], t["id"], end=e["until"], ref=eid)


@host_action("sfx")
def act_sfx(room, data, out):
    name = data.get("name")
    if name not in SFX:
        fail(400, "bad_request")
    eid = action_eid(room, "sfx", data)
    if any(e["ref"] == eid for e in room["effects"]):
        return False
    add_effect(room, "sfx", ref=eid, name=name)


@host_action("star")
def act_star(room, data, out):
    sid = action_eid(room, "star", data)
    if any(s["id"] == sid for s in room["stars"]):
        return False
    now = now_ms()
    bit = next(iter(active_bits(room, now)), None)
    q = current_q(room)
    room["stars"].append({"id": sid, "at": now, "q_index": room["q_index"], "phase": room["phase"],
                          "note": str(data.get("note") or "").strip()[:200],
                          "bit_id": bit["id"] if bit else None,
                          "label": (bit["label"] if bit else (q["text"] if q else None))})


@host_action("profile")
def act_profile(room, data, out):
    prof = {k: re.sub(r"\s+", " ", str(data.get(k) or "")).strip()[:60] for k in ROOM_DEFAULTS["profile"]}
    if prof == room["profile"]:
        return False
    room["profile"] = prof


def clean_question(d, final=False):
    if not isinstance(d, dict):
        fail(400, "bad_question")

    def bi(v, n):
        v = v if isinstance(v, dict) else {"en": v, "vi": v}
        en, vi = str(v.get("en") or "").strip()[:n], str(v.get("vi") or "").strip()[:n]
        return {"en": en or vi, "vi": vi or en}

    kind = "quiz" if final else (d.get("type") if d.get("type") in ("quiz", "poll", "writein") else "quiz")
    try:
        limit = int(d.get("time_limit") or 20)
    except (TypeError, ValueError):
        limit = 20
    q = {"type": kind, "text": bi(d.get("text"), 200), "options": [], "correct": None,
         "time_limit": max(10, min(120, limit)),
         "setup": bi(d.get("setup"), 300), "punchline": bi(d.get("punchline"), 300),
         "notes": str(d.get("notes") or "").strip()[:500]}
    if not q["text"]["en"]:
        fail(400, "bad_question")
    if kind != "writein":
        opts = d.get("options") or []
        if len(opts) != 4:
            fail(400, "bad_question")
        q["options"] = [bi(o, 80) for o in opts]
        if any(not o["en"] for o in q["options"]):
            fail(400, "bad_question")
    if kind == "quiz":
        if d.get("correct") not in (0, 1, 2, 3):
            fail(400, "bad_question")
        q["correct"] = d["correct"]
    if kind == "writein":
        q["demo_answers"] = [str(x)[:80] for x in (d.get("demo_answers") or [])][:12]
    src = d.get("source")
    if isinstance(src, dict) and str(src.get("url", "")).startswith("http"):
        q["source"] = {"title": str(src.get("title") or "")[:200], "url": str(src["url"])[:500]}
    if final:
        q["final"] = True
    return q


@host_action("questions")
def act_questions(room, data, out):
    """Replace the UPCOMING questions (played ones are locked) and the finale."""
    fi = final_index(room)
    if room["phase"] in ("wager", "awards", "podium", "ended") or (fi is not None and room["q_index"] >= fi):
        fail(409, "too_late")
    upcoming = data.get("questions")
    if not isinstance(upcoming, list) or len(upcoming) > 40:
        fail(400, "bad_question")
    cleaned = [clean_question(d) for d in upcoming]
    final = clean_question(data.get("final") or room["questions"][-1], final=True)
    keep = room["questions"][: room["q_index"] + 1] if room["phase"] != "lobby" else []
    room["questions"] = keep + cleaned + [final]


@host_action("draft")
def act_draft(room, data, out):
    """Approve (-> joins the upcoming questions, before the finale) or reject a live draft."""
    d = next((x for x in room["drafts"] if x["id"] == data.get("draft_id")), None)
    if not d:
        return False  # already handled: idempotent
    op = data.get("op")
    if op == "reject":
        room["drafts"].remove(d)
        return
    if op != "approve":
        fail(400, "bad_request")
    fi = final_index(room)
    if room["phase"] in ("wager", "awards", "podium", "ended") or (fi is not None and room["q_index"] >= fi):
        fail(409, "too_late")
    q = clean_question(d)
    at = fi if fi is not None else len(room["questions"])
    room["questions"].insert(at, q)
    room["drafts"].remove(d)


@host_action("viral_send")
def act_viral_send(room, data, out):
    v = room["viral"]
    if room["phase"] in VIRAL_PHASES:
        return False
    if v.get("status") not in ("ready", "used") or len(v.get("cards", [])) < 3:
        fail(409, "viral_not_ready")
    if room["phase"] not in VIRAL_FROM:
        fail(409, "viral_wrong_time")
    start_viral(room)


_bg_tasks: set = set()


@app.post("/api/rooms/{code}/live/{kind}")
async def live_fetch(code: str, kind: str, x_host_key: str | None = Header(None)):
    """Fetch live content (backend only). Runs in the background when live services are
    configured (it can take a while); with no keys it falls back to the backup bank instantly."""
    code = code.upper()
    if kind not in ("weekly", "viral"):
        fail(404, "unknown_action")
    room = await load_room(code)
    require_host(room, x_host_key)
    if kind == "viral" and room["phase"] in VIRAL_PHASES:
        fail(409, "too_late")
    if room[kind]["status"] == "working":
        return view_host(room)

    async def work():
        try:
            result = await (live.build_weekly() if kind == "weekly" else live.build_viral())
        except Exception as exc:  # never surface a raw error: fall back to the backup bank
            print(f"[heckle] live {kind} failed ({type(exc).__name__}); using backup bank")
            result = None

        def store(r):
            res = result
            if res is None:
                picks = random.sample(live.BACKUP_WEEKLY, 6) if kind == "weekly" else random.sample(live.BACKUP_VIRAL, 3)
                res = ({"origin": "backup", "questions": picks, "note": "error"} if kind == "weekly"
                       else {"origin": "backup", "cards": [dict(c, origin="backup") for c in picks]})
            if kind == "weekly":
                r["drafts"] = [{**q, "id": next_id(r, "d"), "origin": res["origin"]} for q in res["questions"]]
                r["weekly"] = {"status": "ready", "origin": res["origin"], "note": res.get("note", "")}
            else:
                r["viral"] = {"status": "ready", "cards": res["cards"], "origin": res["origin"]}

        await mutate(code, store)

    if live.ai_enabled() or live.search_enabled():
        await mutate(code, lambda r: r[kind].update(status="working"))
        task = asyncio.create_task(work())
        _bg_tasks.add(task)
        task.add_done_callback(_bg_tasks.discard)
    else:
        await work()
    return view_host(await load_room(code))


@app.post("/api/rooms/{code}/host/{action}")
async def host(code: str, action: str, request: Request, x_host_key: str | None = Header(None)):
    data = await body_json(request)
    if action not in HOST_ACTIONS:
        fail(404, "unknown_action")
    out = {}

    def fn(room):
        require_host(room, x_host_key)
        # Idempotency for flow buttons: only act if the host saw the same state.
        if "expect_phase" in data and (data["expect_phase"] != room["phase"]
                                       or data.get("expect_q", room["q_index"]) != room["q_index"]):
            out["stale"] = True
            return False
        return HOST_ACTIONS[action](room, data, out)

    room = await mutate(code, fn)
    v = view_host(room)
    v["stale"] = bool(out.get("stale"))
    if "created" in out:
        v["created"] = out["created"]
    return v


@app.get("/api/rooms/{code}/questions")
async def get_questions(code: str, x_host_key: str | None = Header(None)):
    room = await load_room(code)
    require_host(room, x_host_key)
    locked_upto = room["q_index"] if room["phase"] != "lobby" else -1
    return {"questions": [{**q, "i": i, "locked": i <= locked_upto} for i, q in enumerate(room["questions"])],
            "editable": room["phase"] not in ("wager", "awards", "podium", "ended")
            and not (final_index(room) is not None and room["q_index"] >= final_index(room))}


@app.get("/api/rooms/{code}/report")
async def report(code: str, x_host_key: str | None = Header(None)):
    """Host-only set report: per-question breakdown, bits ranked by laughs, stars."""
    room = await load_room(code)
    require_host(room, x_host_key)
    rows = []
    for i, q in enumerate(room["questions"]):
        ans = room["answers"].get(str(i), {})
        counts = [0, 0, 0, 0]
        for a in ans.values():
            if a.get("choice") is not None:
                counts[a["choice"]] += 1
        rows.append({
            "i": i, "type": q["type"], "text": q["text"], "options": q["options"], "correct": q["correct"],
            "played": i in room["revealed"], "answers": len(ans), "counts": counts,
            "correct_count": sum(1 for a in ans.values() if a["correct"]),
        })
    names = {tid: t["name"] for tid, t in room["teams"].items()}
    bits = [{"id": b["id"], "kind": b["kind"], "label": b["label"], "team": names.get(b["team_id"]),
             "q_index": b["q_index"], "laughs": b["laughs"], "groans": b["groans"], "score": bit_score(b),
             "start": b["start"], "duration_s": round(((b["end"] or now_ms()) - b["start"]) / 1000),
             "rating": b.get("rating"), "ratings": b.get("ratings", 0)}
            for b in room["bits"]]
    ranked = sorted(bits, key=lambda b: (-b["score"], -b["laughs"]))
    keep = ranked[:5]
    keep_ids = {b["id"] for b in keep}
    rework = [b for b in sorted(bits, key=lambda b: (b["score"], b["laughs"])) if b["id"] not in keep_ids][:3]
    return {"code": room["_id"], "questions": rows, "bits": ranked, "keep": keep, "rework": rework,
            "stars": room["stars"], "created_at": room["created_at"]}


# ---------------------------------------------------------------- errors + static frontend
@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, dict) else {"error": "server_error"}
    return JSONResponse(status_code=exc.status_code, content=detail)


DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    async def spa(path: str):
        if path.startswith("api/"):
            fail(404, "not_found")
        f = DIST / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
