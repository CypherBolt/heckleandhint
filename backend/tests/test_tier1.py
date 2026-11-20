import json

import pytest
from fastapi.testclient import TestClient

from app import main


class Clock:
    def __init__(self):
        self.t = 1_700_000_000_000

    def __call__(self):
        return self.t


@pytest.fixture
def env(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(main, "now_ms", clock)
    monkeypatch.setattr(main, "_last_text_at", {})
    client = TestClient(main.app)
    r = client.post("/api/rooms").json()
    return client, clock, r["code"], {"X-Host-Key": r["host_key"]}


def join(client, code, device, name="Team", **kw):
    r = client.post(f"/api/rooms/{code}/join", json={"device_id": device, "name": name, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def host(client, code, headers, action, **data):
    r = client.post(f"/api/rooms/{code}/host/{action}", json=data, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def state(client, code, role, **params):
    hdr = params.pop("headers", None)
    return client.get(f"/api/rooms/{code}/state", params={"role": role, **params}, headers=hdr).json()


def expected(ms, limit, streak=0):
    import math
    return int(math.floor(1000 * (1 - (ms / limit) / 2) + 0.5)) + min(100 * streak, 500)


def test_room_code_format(env):
    _, _, code, _ = env
    assert len(code) == 4 and code.isalpha() and code.isupper()
    assert "I" not in code and "O" not in code


def test_three_teams_scores_match_formula(env):
    client, clock, code, H = env
    for d in ("device-aaaa", "device-bbbb", "device-cccc"):
        join(client, code, d, name=d)
    host(client, code, H, "next")  # lobby -> question 0 open
    hs = state(client, code, "host", headers=H)
    q = hs["question"]
    limit = q["time_limit"] * 1000
    right, wrong = q["correct"], (q["correct"] + 1) % 4

    clock.t += 3000
    client.post(f"/api/rooms/{code}/answer", json={"device_id": "device-aaaa", "q_index": 0, "choice": right})
    clock.t += 4500  # B answers at 7.5 s
    client.post(f"/api/rooms/{code}/answer", json={"device_id": "device-bbbb", "q_index": 0, "choice": right})
    clock.t += 1000  # C wrong at 8.5 s -> everyone answered -> auto-lock
    client.post(f"/api/rooms/{code}/answer", json={"device_id": "device-cccc", "q_index": 0, "choice": wrong})
    assert state(client, code, "screen")["phase"] == "question_locked"

    # Points are not added until reveal
    assert all(t["brain"] == 0 for t in state(client, code, "host", headers=H)["teams"])
    hs = host(client, code, H, "next")  # reveal
    scores = {t["name"]: t["brain"] for t in hs["teams"]}
    assert scores["device-aaaa"] == expected(3000, limit)
    assert scores["device-bbbb"] == expected(7500, limit)
    assert scores["device-cccc"] == 0

    # Question 2: streak bonus +100 for A (1 correct in a row before)
    host(client, code, H, "next")  # riff
    host(client, code, H, "next")  # scoreboard
    host(client, code, H, "next")  # q1 open
    q1 = state(client, code, "host", headers=H)["question"]
    clock.t += 2000
    for d in ("device-aaaa", "device-bbbb", "device-cccc"):
        client.post(f"/api/rooms/{code}/answer", json={"device_id": d, "q_index": 1, "choice": q1["correct"]})
    hs = host(client, code, H, "next")  # reveal (auto-locked already)
    scores = {t["name"]: t["brain"] for t in hs["teams"]}
    lim1 = q1["time_limit"] * 1000
    assert scores["device-aaaa"] == expected(3000, limit) + expected(2000, lim1, streak=1)
    assert scores["device-cccc"] == expected(2000, lim1, streak=0)

    # Player sees their own points + rank after reveal
    ps = state(client, code, "player", device="device-aaaa")
    assert ps["my_answer"]["correct"] is True and ps["me"]["rank"] == 1


FORBIDDEN_KEYS = {"correct", "setup", "punchline", "notes", "points", "host_key", "counts"}


def walk_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from walk_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_keys(v)


def test_no_correct_answer_before_reveal(env):
    client, clock, code, H = env
    join(client, code, "device-aaaa", name="A")
    join(client, code, "device-bbbb", name="B")
    host(client, code, H, "next")
    client.post(f"/api/rooms/{code}/answer", json={"device_id": "device-aaaa", "q_index": 0, "choice": 2})
    for phase_step in ("open", "locked"):
        for role, params in (("screen", {}), ("player", {"device": "device-aaaa"}), ("player", {"device": "device-bbbb"})):
            raw = client.get(f"/api/rooms/{code}/state", params={"role": role, **params}).text
            leaked = FORBIDDEN_KEYS & set(walk_keys(json.loads(raw)))
            assert not leaked, (phase_step, role, leaked)
            assert "punchline" not in raw and "Three hearts" not in raw
        if phase_step == "open":
            host(client, code, H, "next")  # lock
    assert state(client, code, "screen")["phase"] == "question_locked"
    # A player cannot pretend to be host to peek
    assert client.get(f"/api/rooms/{code}/state", params={"role": "host"}).status_code == 403
    # After reveal the correct answer IS sent (but never notes/punchline)
    host(client, code, H, "next")
    s = state(client, code, "screen")
    assert s["question"]["correct"] == 2
    raw = json.dumps(s)
    assert "punchline" not in raw and "notes" not in raw


def test_refresh_keeps_team_answer_and_score(env):
    client, clock, code, H = env
    first = join(client, code, "device-keep1", name="Phở Real", emoji="🍜")
    again = join(client, code, "device-keep1", name="Different name")
    assert first["team_id"] == again["team_id"]
    assert state(client, code, "host", headers=H)["team_count"] == 1
    host(client, code, H, "next")
    clock.t += 1000
    client.post(f"/api/rooms/{code}/answer", json={"device_id": "device-keep1", "q_index": 0, "choice": 2})
    # retrying the same answer (bad wifi) is safe
    r = client.post(f"/api/rooms/{code}/answer", json={"device_id": "device-keep1", "q_index": 0, "choice": 1})
    assert r.status_code == 200
    host(client, code, H, "next")  # reveal (auto-locked: only team answered)
    s = state(client, code, "player", device="device-keep1")  # "refresh"
    assert s["me"]["name"] == "Phở Real"
    assert s["my_answer"]["choice"] == 2
    assert s["me"]["brain"] == expected(1000, 20000)


def test_host_actions_without_key_are_403(env):
    client, clock, code, H = env
    for action in ("next", "back", "skip", "reset", "add_time", "freeze", "demo_load", "demo_sim", "blackout", "mod"):
        assert client.post(f"/api/rooms/{code}/host/{action}", json={}).status_code == 403
        assert client.post(f"/api/rooms/{code}/host/{action}", json={},
                           headers={"X-Host-Key": "wrong"}).status_code == 403
    assert client.get(f"/api/rooms/{code}/state", params={"role": "host"}).status_code == 403


def test_demo_teams_appear_and_answer(env):
    client, clock, code, H = env
    host(client, code, H, "demo_load")
    host(client, code, H, "demo_load")  # idempotent
    s = state(client, code, "screen")
    assert s["team_count"] == 8 and len(s["teams"]) == 8  # immediately (< 2 s)
    host(client, code, H, "demo_sim", on=True)
    host(client, code, H, "next")
    assert state(client, code, "screen")["answered_count"] == 0
    clock.t += 1999
    assert state(client, code, "screen")["answered_count"] == 0  # nobody before 2 s
    clock.t += 4001  # 6 s after open -> all 8 answered -> auto-lock
    s = state(client, code, "screen")
    assert s["phase"] == "question_locked"
    hs = state(client, code, "host", headers=H)
    assert len(hs["answers"]) == 8
    assert all(2000 <= a["ms"] <= 6000 for a in hs["answers"].values())


def test_demo_accuracy_is_about_60_percent(env):
    client, clock, code, H = env
    host(client, code, H, "demo_load")
    host(client, code, H, "demo_sim", on=True)
    right = total = 0
    host(client, code, H, "next")
    for _ in range(40):
        clock.t += 7000
        hs = state(client, code, "host", headers=H)
        if hs["question"]["type"] != "poll":
            right += sum(1 for a in hs["answers"].values() if a["correct"])
            total += len(hs["answers"])
        host(client, code, H, "reset")
        host(client, code, H, "next")
    assert 0.45 < right / total < 0.75


def test_timer_auto_lock_add_time_and_freeze(env):
    client, clock, code, H = env
    join(client, code, "device-aaaa", name="A")
    hs = host(client, code, H, "next")
    host(client, code, H, "add_time")
    clock.t += 25000  # 20 s + 10 s extra not reached yet
    assert state(client, code, "screen")["phase"] == "question_open"
    host(client, code, H, "freeze", frozen=True)
    clock.t += 60000
    assert state(client, code, "screen")["phase"] == "question_open"
    host(client, code, H, "freeze", frozen=False)
    clock.t += 5001
    assert state(client, code, "screen")["phase"] == "question_locked"


def test_next_is_idempotent_with_expect(env):
    client, clock, code, H = env
    join(client, code, "device-aaaa", name="A")
    host(client, code, H, "next", expect_phase="lobby", expect_q=-1)
    r = host(client, code, H, "next", expect_phase="lobby", expect_q=-1)  # retried tap
    assert r["stale"] is True and r["phase"] == "question_open"


def test_version_no_change(env):
    client, clock, code, H = env
    s = state(client, code, "screen")
    again = state(client, code, "screen", since=s["version"])
    assert again == {"unchanged": True, "version": s["version"], "server_now": clock.t}


def test_text_filter_and_moderation(env):
    client, clock, code, H = env
    join(client, code, "device-bad1", name="fuck this", fact="call me 0903 123 456")
    join(client, code, "device-ok11", name="Bún Voyage", fact="we love chè")
    s = state(client, code, "screen")
    names = {t["n"]: t["name"] for t in s["teams"]}
    assert names[1] is None and names[2] == "Bún Voyage"  # flagged name held back
    assert all(t["fact"] is None for t in s["teams"])  # facts need approval
    hs = state(client, code, "host", headers=H)
    bad = hs["teams"][0]
    assert bad["name_status"] == "pending" and "0903" not in bad["fact"]  # phone stripped
    host(client, code, H, "mod", team_id=hs["teams"][1]["id"], field="fact", op="approve")
    assert state(client, code, "screen")["teams"][1]["fact"] == "we love chè"
    host(client, code, H, "blackout", on=True)
    s = state(client, code, "screen")
    assert all(t["name"] is None and t["fact"] is None for t in s["teams"])


def test_text_rate_limit_per_device(env, monkeypatch):
    client, clock, code, H = env
    monkeypatch.setattr(main, "_last_text_at", {})
    join(client, code, "device-rate1", name="A")
    other = client.post("/api/rooms").json()["code"]
    r = client.post(f"/api/rooms/{other}/join", json={"device_id": "device-rate1", "name": "B"})
    assert r.status_code == 429 and r.json()["error"] == "too_fast"
    clock.t += 8000
    assert client.post(f"/api/rooms/{other}/join", json={"device_id": "device-rate1", "name": "B"}).status_code == 200


def test_max_30_teams(env):
    client, clock, code, H = env
    for k in range(30):
        join(client, code, f"device-{k:04d}", name=f"T{k}")
    r = client.post(f"/api/rooms/{code}/join", json={"device_id": "device-late", "name": "Late"})
    assert r.status_code == 409 and r.json()["error"] == "room_full"


def test_full_question_run_to_end(env):
    """Every question can be played through to the end (Tier 2 adds wager + awards + podium)."""
    client, clock, code, H = env
    host(client, code, H, "demo_load")
    host(client, code, H, "demo_sim", on=True)
    total = state(client, code, "screen")["q_total"]
    host(client, code, H, "next")
    played = 0
    while state(client, code, "screen")["phase"] not in ("awards",):
        if state(client, code, "screen")["phase"] == "wager":
            assert host(client, code, H, "next")["phase"] == "question_open"
        clock.t += 7000
        assert state(client, code, "screen")["phase"] == "question_locked"
        for expect in ("reveal", "riff", "scoreboard"):
            assert host(client, code, H, "next")["phase"] == expect
        host(client, code, H, "next")
        played += 1
    assert played == total
    assert host(client, code, H, "next")["phase"] == "podium"
    assert host(client, code, H, "next")["phase"] == "ended"
    assert host(client, code, H, "back")["phase"] == "podium"
