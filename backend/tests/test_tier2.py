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
    monkeypatch.setattr(main, "_react_hist", {})
    client = TestClient(main.app)
    r = client.post("/api/rooms").json()
    return client, clock, r["code"], {"X-Host-Key": r["host_key"]}


def join(client, code, device, name="Team", **kw):
    r = client.post(f"/api/rooms/{code}/join", json={"device_id": device, "name": name, **kw})
    assert r.status_code == 200, r.text
    return r.json()["team_id"]


def host(client, code, H, action, expect_status=200, **data):
    r = client.post(f"/api/rooms/{code}/host/{action}", json=data, headers=H)
    assert r.status_code == expect_status, r.text
    return r.json()


def state(client, code, role, **params):
    hdr = params.pop("headers", None)
    return client.get(f"/api/rooms/{code}/state", params={"role": role, **params}, headers=hdr).json()


def raw(client, code, role, **params):
    return client.get(f"/api/rooms/{code}/state", params={"role": role, **params}).text


def goto_question(client, clock, code, H, qtype):
    """Advance (skipping) until the current question has the given type."""
    host(client, code, H, "next")
    for _ in range(40):
        hs = state(client, code, "host", headers=H)
        if hs["phase"] == "question_open" and hs["question"]["type"] == qtype:
            return hs
        host(client, code, H, "skip")
    raise AssertionError("question type not found")


# ------------------------------------------------------------------ required Tier 2 tests
def test_unapproved_text_never_reaches_players_or_screen(env):
    client, clock, code, H = env
    a = join(client, code, "device-aaaa", name="A", fact="SECRETFACT one")
    join(client, code, "device-bbbb", name="B")
    join(client, code, "device-cccc", name="C")
    clock.t += 9000
    hs = goto_question(client, clock, code, H, "writein")
    i = hs["question"]["i"]
    for d, txt in (("device-aaaa", "GREENJOKE about rain"), ("device-bbbb", "UNAPPROVEDJOKE one"),
                   ("device-cccc", "fuck HIDDENJOKE")):
        r = client.post(f"/api/rooms/{code}/answer", json={"device_id": d, "q_index": i, "text": txt})
        assert r.status_code == 200, r.text
    clock.t += 9000  # 8 s text cooldown after the write-in
    r = client.post(f"/api/rooms/{code}/heckle", json={"device_id": "device-bbbb", "id": "x1", "text": "PENDINGHECKLE lol"})
    assert r.status_code == 200, r.text

    own = {"device-bbbb": "UNAPPROVEDJOKE", "device-cccc": "HIDDENJOKE"}  # a phone may see its OWN text

    def leaks(markers):
        found = []
        for role, params in (("screen", {}), ("player", {"device": "device-bbbb"}), ("player", {"device": "device-cccc"})):
            body = raw(client, code, role, **params)
            found += [(role, params.get("device"), m) for m in markers if m in body and own.get(params.get("device")) != m]
        return found

    secret = ["SECRETFACT", "UNAPPROVEDJOKE", "HIDDENJOKE", "PENDINGHECKLE"]
    assert state(client, code, "screen")["phase"] == "question_locked"
    assert leaks(secret + ["GREENJOKE"]) == []
    hs = state(client, code, "host", headers=H)
    groups = {g["text"].split()[0]: g for g in hs["writeins"]}
    assert groups["fuck"]["flagged"] is True  # filter flags it for the host
    host(client, code, H, "wi_mod", gid=groups["GREENJOKE"]["gid"], op="approve")
    host(client, code, H, "wi_mod", gid=groups["fuck"]["gid"], op="hide")
    assert leaks(secret + ["GREENJOKE"]) == []  # still locked: nothing yet
    host(client, code, H, "next")  # -> vote
    assert state(client, code, "screen")["phase"] == "vote"
    assert leaks(secret) == []
    assert "GREENJOKE" in raw(client, code, "screen")  # approved text is allowed now
    host(client, code, H, "next")  # reveal
    host(client, code, H, "next")  # riff
    assert leaks(secret) == []
    # heckle only reaches the TV once the host shows it, never other phones
    hid = state(client, code, "host", headers=H)["heckles"][0]["id"]
    host(client, code, H, "heckle", heckle_id=hid, op="show")
    assert "PENDINGHECKLE" in raw(client, code, "screen")
    assert "PENDINGHECKLE" not in raw(client, code, "player", device="device-cccc")
    host(client, code, H, "blackout", on=True)
    assert "PENDINGHECKLE" not in raw(client, code, "screen")
    assert "GREENJOKE" not in raw(client, code, "screen")


def test_laugh_rate_limit_holds(env):
    client, clock, code, H = env
    join(client, code, "device-aaaa", name="A")
    r = client.post(f"/api/rooms/{code}/react", json={"device_id": "device-aaaa", "laughs": 10}).json()
    assert r["accepted"]["laughs"] == 4
    r = client.post(f"/api/rooms/{code}/react", json={"device_id": "device-aaaa", "laughs": 3, "groans": 2}).json()
    assert r["accepted"] == {"laughs": 0, "groans": 0}
    clock.t += 500
    r = client.post(f"/api/rooms/{code}/react", json={"device_id": "device-aaaa", "laughs": 3}).json()
    assert r["accepted"]["laughs"] == 0  # still inside the same second
    clock.t += 501
    r = client.post(f"/api/rooms/{code}/react", json={"device_id": "device-aaaa", "laughs": 3, "groans": 3}).json()
    assert r["accepted"] == {"laughs": 3, "groans": 1}
    # 60 fast requests over 3 seconds can never exceed 4/s
    total = 0
    for _ in range(60):
        clock.t += 50
        total += client.post(f"/api/rooms/{code}/react", json={"device_id": "device-aaaa", "laughs": 4}).json()["accepted"]["laughs"]
    assert total <= 4 * 3 + 4
    s = state(client, code, "screen")
    assert sum(x[1] for x in s["react_log"]) <= 4 * 6
    # not a player -> refused
    assert client.post(f"/api/rooms/{code}/react", json={"device_id": "nobody-xx", "laughs": 1}).status_code == 404


def test_roast_card_blocked_for_off_teams(env):
    client, clock, code, H = env
    off = join(client, code, "device-off1", name="Off team", roast="off")
    mild = join(client, code, "device-mld1", name="Mild team", roast="mild", mic=False)
    spicy = join(client, code, "device-spc1", name="Spicy team", roast="spicy", mic=True)
    r = client.post(f"/api/rooms/{code}/host/roast", json={"team_id": off}, headers=H)
    assert r.status_code == 409 and r.json()["error"] == "roast_off"
    assert not any(e["kind"] == "roast" for e in state(client, code, "host", headers=H)["effects"])
    host(client, code, H, "roast", team_id=mild, action_id="r1")
    host(client, code, H, "roast", team_id=mild, action_id="r1")  # retry: no duplicate
    effects = state(client, code, "host", headers=H)["effects"]
    assert len([e for e in effects if e["kind"] == "roast"]) == 1
    ps = state(client, code, "player", device="device-mld1")
    assert [e["kind"] for e in ps["effects"]] == ["roast"]  # only that team's phone turns red
    assert state(client, code, "player", device="device-spc1")["effects"] == []
    assert any(e["kind"] == "roast" for e in state(client, code, "screen")["effects"])  # TV shakes
    # Spotlight only for mic-ready teams
    r = client.post(f"/api/rooms/{code}/host/spotlight", json={"team_id": mild}, headers=H)
    assert r.status_code == 409 and r.json()["error"] == "not_mic_ready"
    host(client, code, H, "spotlight", team_id=spicy)
    # without the host key: 403
    assert client.post(f"/api/rooms/{code}/host/roast", json={"team_id": spicy}).status_code == 403


def test_full_night_lobby_to_follow_card(env):
    client, clock, code, H = env
    me = join(client, code, "device-real", name="Real Team", roast="spicy", mic=True)
    host(client, code, H, "profile", host_name="Minh Comedy", instagram="minh.comedy", zalo="minhcomedy",
         facebook="minhcomedy", tiktok="@minhcomedy")
    host(client, code, H, "demo_load")
    host(client, code, H, "demo_sim", on=True)
    clock.t += 9000
    host(client, code, H, "next")
    seen = set()
    for _ in range(200):
        hs = state(client, code, "host", headers=H)
        p = hs["phase"]
        seen.add(p)
        if p == "ended":
            break
        if p == "question_open":
            q = hs["question"]
            if q["type"] == "writein":
                client.post(f"/api/rooms/{code}/answer", json={"device_id": "device-real", "q_index": q["i"], "text": "Our real joke"})
            else:
                client.post(f"/api/rooms/{code}/answer", json={"device_id": "device-real", "q_index": q["i"], "choice": 0})
            clock.t += 9000
            continue
        if p == "question_locked" and hs["question"]["type"] == "writein":
            for g in hs["writeins"][:6]:
                host(client, code, H, "wi_mod", gid=g["gid"], op="approve")
            host(client, code, H, "next")
            ps = state(client, code, "player", device="device-real")
            assert ps["phase"] == "vote"
            seen.add("vote")
            mine = set(ps["my_groups"])
            target = next(c["gid"] for c in ps["question"]["choices"] if c["gid"] not in mine)
            client.post(f"/api/rooms/{code}/vote", json={"device_id": "device-real", "q_index": hs["q_index"], "gid": target})
            clock.t += 5000
            continue
        if p == "riff":
            client.post(f"/api/rooms/{code}/react", json={"device_id": "device-real", "laughs": 4})
            clock.t += 3000
        if p == "wager":
            r = client.post(f"/api/rooms/{code}/wager", json={"device_id": "device-real", "pct": 50})
            assert r.json()["wager"]["pct"] == 50
        if p == "reveal" and hs["question"]["type"] == "quiz" and not hs["question"].get("final"):
            host(client, code, H, "style", team_id=me, action_id=f"s{hs['q_index']}")
        host(client, code, H, "next")
    assert {"lobby", "question_open", "question_locked", "vote", "reveal", "riff", "scoreboard",
            "wager", "awards", "podium", "ended"} - seen == {"lobby"}  # lobby was before the loop
    ps = state(client, code, "player", device="device-real")
    assert ps["phase"] == "ended"
    assert ps["profile"]["instagram"] == "minh.comedy"  # follow card data
    assert {a["key"] for a in ps["awards"]} >= {"champion", "funniest", "confidently_wrong"}
    rc = client.get(f"/api/rooms/{code}/recap").json()
    assert len(rc["top"]) == 3 and rc["funniest_answer"] is not None
    rep = client.get(f"/api/rooms/{code}/report", headers=H).json()
    assert rep["bits"] and len(rep["keep"]) <= 5 and len(rep["rework"]) <= 3


# ------------------------------------------------------------------ feature details
def test_writein_grouping_votes_and_laugh_points(env):
    client, clock, code, H = env
    a, b, c = (join(client, code, f"device-{x}{x}{x}{x}", name=x) for x in "abc")
    clock.t += 9000
    hs = goto_question(client, clock, code, H, "writein")
    i = hs["question"]["i"]
    for d, txt in (("device-aaaa", "Just ice"), ("device-bbbb", "just ice!!"), ("device-cccc", "Durian & mayo")):
        client.post(f"/api/rooms/{code}/answer", json={"device_id": d, "q_index": i, "text": txt})
    hs = state(client, code, "host", headers=H)
    assert len(hs["writeins"]) == 2  # duplicates grouped
    ice = next(g for g in hs["writeins"] if len(g["teams"]) == 2)
    durian = next(g for g in hs["writeins"] if len(g["teams"]) == 1)
    host(client, code, H, "wi_mod", gid=ice["gid"], op="approve")
    host(client, code, H, "wi_mod", gid=durian["gid"], op="approve")
    host(client, code, H, "next")  # vote
    r = client.post(f"/api/rooms/{code}/vote", json={"device_id": "device-aaaa", "q_index": i, "gid": ice["gid"]})
    assert r.status_code == 409 and r.json()["error"] == "own_answer"
    client.post(f"/api/rooms/{code}/vote", json={"device_id": "device-aaaa", "q_index": i, "gid": durian["gid"]})
    client.post(f"/api/rooms/{code}/vote", json={"device_id": "device-bbbb", "q_index": i, "gid": durian["gid"]})
    client.post(f"/api/rooms/{code}/vote", json={"device_id": "device-cccc", "q_index": i, "gid": ice["gid"]})
    hs = state(client, code, "host", headers=H)
    assert hs["phase"] == "reveal"  # everyone voted -> auto reveal
    laugh = {t["name"]: t["laugh"] for t in hs["teams"]}
    assert laugh == {"a": 100, "b": 100, "c": 400}
    host(client, code, H, "back")  # un-reveal removes the points
    assert all(t["laugh"] == 0 for t in state(client, code, "host", headers=H)["teams"])


def test_max_six_approvals(env):
    client, clock, code, H = env
    for k in range(8):
        join(client, code, f"device-{k:04d}", name=f"T{k}")
    clock.t += 9000
    hs = goto_question(client, clock, code, H, "writein")
    for k in range(8):
        client.post(f"/api/rooms/{code}/answer", json={"device_id": f"device-{k:04d}", "q_index": hs["question"]["i"], "text": f"answer number {k}"})
    groups = state(client, code, "host", headers=H)["writeins"]
    for g in groups[:6]:
        host(client, code, H, "wi_mod", gid=g["gid"], op="approve")
    r = client.post(f"/api/rooms/{code}/host/wi_mod", json={"gid": groups[6]["gid"], "op": "approve"}, headers=H)
    assert r.status_code == 409 and r.json()["error"] == "max_six"


def test_style_points_undo_and_heckle_points(env):
    client, clock, code, H = env
    a = join(client, code, "device-aaaa", name="A")
    hs = host(client, code, H, "style", team_id=a, action_id="tap1")
    eid = hs["created"]
    host(client, code, H, "style", team_id=a, action_id="tap1")  # retry: still +200 once
    assert state(client, code, "host", headers=H)["teams"][0]["laugh"] == 200
    assert any(e["kind"] == "style" for e in state(client, code, "player", device="device-aaaa")["effects"])
    host(client, code, H, "undo", entry_id=eid)
    assert state(client, code, "host", headers=H)["teams"][0]["laugh"] == 0
    clock.t += 9000  # joining counted as a text submission
    client.post(f"/api/rooms/{code}/heckle", json={"device_id": "device-aaaa", "id": "h1", "text": "Your jokes need Wi-Fi"})
    client.post(f"/api/rooms/{code}/heckle", json={"device_id": "device-aaaa", "id": "h1", "text": "Your jokes need Wi-Fi"})
    hs = state(client, code, "host", headers=H)
    assert len(hs["heckles"]) == 1 and hs["teams"][0]["laugh"] == 0
    r = client.post(f"/api/rooms/{code}/heckle", json={"device_id": "device-aaaa", "id": "h2", "text": "again"})
    assert r.status_code == 429  # one text per 8 s
    host(client, code, H, "heckle", heckle_id=hs["heckles"][0]["id"], op="show")
    s = state(client, code, "screen")
    assert [e["text"] for e in s["effects"] if e["kind"] == "heckle"] == ["Your jokes need Wi-Fi"]
    assert state(client, code, "host", headers=H)["teams"][0]["laugh"] == 100
    clock.t += 8001
    assert not [e for e in state(client, code, "screen")["effects"] if e["kind"] == "heckle"]


def test_wager_bottom_three_get_double(env):
    client, clock, code, H = env
    ids = [join(client, code, f"device-{k:04d}", name=f"T{k}") for k in range(5)]
    host(client, code, H, "questions", questions=[], final=None)  # just the finale left
    host(client, code, H, "next")
    hs = state(client, code, "host", headers=H)
    assert hs["phase"] == "wager"
    bottom = hs["wager"]["bottom"]
    assert len(bottom) == 3
    # give one team some style points first so the wager has something to bet
    for t in ids:
        host(client, code, H, "style", team_id=t, action_id=f"s-{t}")
    host(client, code, H, "back")  # re-snapshot totals
    host(client, code, H, "next")
    hs = state(client, code, "host", headers=H)
    bottom = hs["wager"]["bottom"]
    for k in range(5):
        client.post(f"/api/rooms/{code}/wager", json={"device_id": f"device-{k:04d}", "pct": 100})
    host(client, code, H, "next")  # finale open
    q = state(client, code, "host", headers=H)["question"]
    assert q["final"]
    for k in range(5):
        client.post(f"/api/rooms/{code}/answer", json={"device_id": f"device-{k:04d}", "q_index": q["i"], "choice": q["correct"] if k < 4 else 1})
    hs = host(client, code, H, "next")  # reveal
    by = {t["id"]: t for t in hs["teams"]}
    for k, tid in enumerate(ids):
        base = by[tid]["brain"] - (state(client, code, "player", device=f"device-{k:04d}")["wager_delta"])
        delta = state(client, code, "player", device=f"device-{k:04d}")["wager_delta"]
        if k == 4:
            assert delta == -200
        else:
            assert delta == (400 if tid in bottom else 200)


def test_question_editor(env):
    client, clock, code, H = env
    qs = client.get(f"/api/rooms/{code}/questions", headers=H).json()["questions"]
    assert qs[-1]["final"]
    new = [{"type": "quiz", "text": {"en": "Is phở soup?", "vi": "Phở có phải súp không?"},
            "options": [{"en": "Yes", "vi": "Có"}, {"en": "No", "vi": "Không"}, {"en": "Maybe", "vi": "Có thể"}, {"en": "Lunch", "vi": "Bữa trưa"}],
            "correct": 0, "time_limit": 15},
           {"type": "writein", "text": {"en": "Name a bar snack"}}]
    host(client, code, H, "questions", questions=new)
    qs = client.get(f"/api/rooms/{code}/questions", headers=H).json()["questions"]
    assert [q["type"] for q in qs] == ["quiz", "writein", "quiz"] and qs[-1]["final"]
    assert qs[1]["text"]["vi"] == "Name a bar snack"  # missing language falls back
    bad = client.post(f"/api/rooms/{code}/host/questions", json={"questions": [{"type": "quiz", "text": {"en": "x"}, "options": [], "correct": 0}]}, headers=H)
    assert bad.status_code == 400 and bad.json()["error"] == "bad_question"
    join(client, code, "device-aaaa", name="A")
    host(client, code, H, "next")  # now playing q0: it becomes locked
    host(client, code, H, "questions", questions=[])  # drop upcoming write-in
    qs = client.get(f"/api/rooms/{code}/questions", headers=H).json()["questions"]
    assert qs[0]["text"]["en"] == "Is phở soup?" and qs[0]["locked"] and len(qs) == 2


def test_riff_fuel_chips(env):
    client, clock, code, H = env
    for k in range(6):
        join(client, code, f"device-{k:04d}", name=f"T{k}")
    host(client, code, H, "next")
    q = state(client, code, "host", headers=H)["question"]
    right = q["correct"]
    wrong = (right + 1) % 4
    lone = (right + 2) % 4
    picks = [right, right, wrong, wrong, wrong, lone]
    for k, ch in enumerate(picks):
        clock.t += 500
        client.post(f"/api/rooms/{code}/answer", json={"device_id": f"device-{k:04d}", "q_index": 0, "choice": ch})
    kinds = {c["kind"]: c for c in state(client, code, "host", headers=H)["riff_fuel"]}
    assert kinds["popular"]["option"] == wrong
    assert kinds["lone_wolf"]["option"] == lone
    assert kinds["split"]["options"] == [wrong, right]
    assert kinds["confidently_wrong"]["option"] == wrong
    assert kinds["fastest_wrong"]["teams"] == ["t3"]
    assert "rivals" in kinds  # everyone on 0 points -> within 300


def test_bits_recorded_with_laughs_and_stars(env):
    client, clock, code, H = env
    join(client, code, "device-aaaa", name="A")
    join(client, code, "device-bbbb", name="B")
    host(client, code, H, "next")
    host(client, code, H, "next")  # lock
    host(client, code, H, "next")  # reveal
    host(client, code, H, "next")  # riff -> bit starts
    for d in ("device-aaaa", "device-bbbb"):
        client.post(f"/api/rooms/{code}/react", json={"device_id": d, "laughs": 4})
    host(client, code, H, "star", note="octopus heart bit killed", action_id="st1")
    host(client, code, H, "star", note="octopus heart bit killed", action_id="st1")
    host(client, code, H, "next")  # scoreboard -> bit closes
    clock.t += 2000
    client.post(f"/api/rooms/{code}/react", json={"device_id": "device-aaaa", "laughs": 4})  # outside the bit
    rep = client.get(f"/api/rooms/{code}/report", headers=H).json()
    assert rep["bits"][0]["laughs"] == 8 and rep["bits"][0]["score"] == 4.0
    assert len(rep["stars"]) == 1 and rep["stars"][0]["note"] == "octopus heart bit killed"
    assert client.get(f"/api/rooms/{code}/report").status_code == 403


def test_sfx_reaches_screen_only(env):
    client, clock, code, H = env
    join(client, code, "device-aaaa", name="A")
    host(client, code, H, "sfx", name="rimshot", action_id="x")
    assert [e["name"] for e in state(client, code, "screen")["effects"]] == ["rimshot"]
    assert state(client, code, "player", device="device-aaaa")["effects"] == []
    assert client.post(f"/api/rooms/{code}/host/sfx", json={"name": "laser"}, headers=H).status_code == 400
