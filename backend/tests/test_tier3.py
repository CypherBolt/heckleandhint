import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app import live, main


class Clock:
    def __init__(self):
        self.t = 1_700_000_000_000

    def __call__(self):
        return self.t


@pytest.fixture
def env(monkeypatch):
    # Tier 3 must work with NO keys at all.
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "YDC_API_KEY"):
        monkeypatch.delenv(k, raising=False)
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


# ------------------------------------------------------------------ no keys: silent fallbacks
def test_status_reports_no_live_services(env):
    client, clock, code, H = env
    assert state(client, code, "host", headers=H)["live"] == {"ai": False, "search": False}


def test_moderation_falls_back_to_word_filter():
    bad = asyncio.run(live.moderate("fuck this quiz", 30))
    ok = asyncio.run(live.moderate("Phở Real", 30))
    assert bad["flagged"] and bad["mod_source"] == "filter"
    assert not ok["flagged"] and ok["mod_source"] == "filter"


def test_weekly_without_keys_uses_backup_bank_with_sources(env):
    client, clock, code, H = env
    join(client, code, "device-aaaa", name="A")
    hs = client.post(f"/api/rooms/{code}/live/weekly", headers=H).json()
    assert hs["weekly"]["status"] == "ready" and hs["weekly"]["origin"] == "backup"
    drafts = hs["drafts"]
    assert len(drafts) == 6
    for d in drafts:
        assert d["source"]["url"].startswith("https://") and d["source"]["title"]
        assert not live.BANNED.search(json.dumps(d, ensure_ascii=False))
    # drafts are host-only until approved
    for role, params in (("screen", {}), ("player", {"device": "device-aaaa"})):
        body = raw(client, code, role, **params)
        assert all(d["text"]["en"] not in body for d in drafts)
    # without the key: 403
    assert client.post(f"/api/rooms/{code}/live/weekly").status_code == 403


def test_approve_and_reject_drafts_and_source_after_reveal(env):
    client, clock, code, H = env
    join(client, code, "device-aaaa", name="A")
    drafts = client.post(f"/api/rooms/{code}/live/weekly", headers=H).json()["drafts"]
    total = state(client, code, "host", headers=H)["q_total"]
    host(client, code, H, "draft", draft_id=drafts[0]["id"], op="approve")
    host(client, code, H, "draft", draft_id=drafts[0]["id"], op="approve")  # retry: idempotent
    host(client, code, H, "draft", draft_id=drafts[1]["id"], op="reject")
    hs = state(client, code, "host", headers=H)
    assert hs["q_total"] == total + 1 and len(hs["drafts"]) == 4
    qs = client.get(f"/api/rooms/{code}/questions", headers=H).json()["questions"]
    assert qs[-1]["final"] and qs[-2]["text"] == drafts[0]["text"]  # inserted just before the finale
    # play it: jump straight to it by editing the list down to just that question
    host(client, code, H, "questions", questions=[qs[-2]])
    host(client, code, H, "next")
    s = state(client, code, "screen")
    assert "source" not in s["question"]  # nothing that hints at the answer before reveal
    client.post(f"/api/rooms/{code}/answer", json={"device_id": "device-aaaa", "q_index": 0, "choice": 0})
    host(client, code, H, "next")  # reveal
    assert state(client, code, "screen")["question"]["source"]["url"] == drafts[0]["source"]["url"]


def test_viral_drop_full_flow_without_keys(env):
    client, clock, code, H = env
    for k in range(3):
        join(client, code, f"device-{k:04d}", name=f"T{k}")
    hs = client.post(f"/api/rooms/{code}/live/viral", headers=H).json()
    cards = hs["viral"]["cards"]
    assert hs["viral"]["status"] == "ready" and len(cards) == 3
    assert all(c["credit"] and len(c["angles"]) == 3 for c in cards)
    host(client, code, H, "viral_send")
    s = state(client, code, "screen")
    assert s["phase"] == "viral_vote" and len(s["viral"]["cards"]) == 3
    # the comedian's private joke angles never reach the TV or phones
    for role, params in (("screen", {}), ("player", {"device": "device-0000"})):
        body = raw(client, code, role, **params)
        assert "angles" not in body and cards[0]["angles"][0] not in body
    for k, idx in enumerate((2, 2, 0)):
        client.post(f"/api/rooms/{code}/viral_vote", json={"device_id": f"device-{k:04d}", "idx": idx})
    s = state(client, code, "screen")
    assert s["phase"] == "viral_riff" and s["viral"]["winner"] == 2
    client.post(f"/api/rooms/{code}/react", json={"device_id": "device-0000", "laughs": 4})
    clock.t += 60001  # 60 s riff ends -> the room rates it
    assert state(client, code, "screen")["phase"] == "viral_rate"
    for k, stars in enumerate((5, 4, 3)):
        client.post(f"/api/rooms/{code}/viral_rate", json={"device_id": f"device-{k:04d}", "stars": stars})
    s = state(client, code, "screen")
    assert s["phase"] == "viral_result" and s["viral"]["rating"] == 4.0
    assert host(client, code, H, "next")["phase"] == "lobby"  # back to where we were
    bit = next(b for b in client.get(f"/api/rooms/{code}/report", headers=H).json()["bits"] if b["kind"] == "viral")
    assert bit["laughs"] == 4 and bit["rating"] == 4.0 and bit["ratings"] == 3


def test_viral_only_between_questions(env):
    client, clock, code, H = env
    join(client, code, "device-aaaa", name="A")
    host(client, code, H, "viral_send", expect_status=409)  # nothing fetched yet
    client.post(f"/api/rooms/{code}/live/viral", headers=H)
    host(client, code, H, "next")  # question open
    r = client.post(f"/api/rooms/{code}/host/viral_send", json={}, headers=H)
    assert r.status_code == 409 and r.json()["error"] == "viral_wrong_time"


def test_viral_with_demo_crowd(env):
    client, clock, code, H = env
    host(client, code, H, "demo_load")
    host(client, code, H, "demo_sim", on=True)
    client.post(f"/api/rooms/{code}/live/viral", headers=H)
    host(client, code, H, "viral_send")
    clock.t += 6500
    assert state(client, code, "screen")["phase"] == "viral_riff"  # all 8 demo teams voted
    clock.t += 61000
    assert state(client, code, "screen")["phase"] == "viral_rate"
    clock.t += 6000
    s = state(client, code, "screen")
    assert s["phase"] == "viral_result" and 3 <= s["viral"]["rating"] <= 5


# ------------------------------------------------------------------ live paths, with stand-in services
NEWS = [{"title": f"Saigon story {i}", "url": f"https://news.example/{i}", "snippet": "A food festival opened.",
         "source": "news.example", "age": "2 days"} for i in range(6)]


def fake_q(i, **kw):
    q = {"text": {"en": f"Live question {i}?", "vi": f"Câu hỏi {i}?"},
         "options": [{"en": "A", "vi": "A"}, {"en": "B", "vi": "B"}, {"en": "C", "vi": "C"}, {"en": "D", "vi": "D"}],
         "correct": 1, "setup": {"en": "s", "vi": "s"}, "punchline": {"en": "p", "vi": "p"}, "source_index": i % 6}
    q.update(kw)
    return q


def test_weekly_live_path_filters_banned_topics_and_bad_sources(monkeypatch):
    async def fake_search(query, count=8):
        return NEWS

    async def fake_claude(system, user, schema, **kw):
        return {"questions": [fake_q(0), fake_q(1), fake_q(2), fake_q(3),
                              fake_q(4, text={"en": "Who did the police arrest?", "vi": "Công an bắt ai?"}),
                              fake_q(5, source_index=99)]}

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(live, "search", fake_search)
    monkeypatch.setattr(live, "claude_json", fake_claude)
    res = asyncio.run(live.build_weekly())
    assert res["origin"] == "live" and len(res["questions"]) == 4  # crime + invented source dropped
    assert all(q["source"]["url"].startswith("https://news.example/") for q in res["questions"])


def test_weekly_falls_back_when_search_down_or_ai_fails(monkeypatch):
    async def no_search(query, count=8):
        return None

    async def broken_claude(*a, **kw):
        return None

    monkeypatch.setattr(live, "search", no_search)
    assert asyncio.run(live.build_weekly())["origin"] == "backup"

    async def fake_search(query, count=8):
        return NEWS

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(live, "search", fake_search)
    monkeypatch.setattr(live, "claude_json", broken_claude)
    res = asyncio.run(live.build_weekly())
    assert res["origin"] == "backup" and len(res["questions"]) == 6


def test_search_times_out_after_6_seconds(monkeypatch):
    class SlowClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **kw):
            await asyncio.sleep(30)

    import httpx2

    monkeypatch.setenv("YDC_API_KEY", "test")
    monkeypatch.setattr(httpx2, "AsyncClient", SlowClient)
    monkeypatch.setattr(live, "SEARCH_TIMEOUT_S", 0.05)  # same code path, shortened for the test
    assert asyncio.run(live.search("saigon")) is None


def test_search_result_shapes():
    v1 = {"results": {"web": [{"url": "https://a.vn/1", "title": "A", "description": "d"}],
                      "news": [{"url": "https://b.vn/2", "title": "B", "description": "n", "page_age": "1d"}]}}
    legacy = {"hits": [{"url": "https://c.vn/3", "title": "C", "snippets": ["s"]}]}
    assert [r["title"] for r in live._parse_results(v1)] == ["B", "A"]
    assert live._parse_results(legacy)[0]["snippet"] == "s"
    assert live._parse_results({"weird": 1}) == []


def test_viral_live_path_backfills_from_bank(monkeypatch):
    async def fake_search(query, count=8):
        return NEWS

    async def fake_claude(*a, **kw):
        return {"cards": [{"title": "Durian latte", "text": "A café sells durian lattes.", "source_index": 0,
                           "angles": ["a", "b", "c"]},
                          {"title": "Bad one", "text": "A crash on the bridge", "source_index": 1, "angles": ["a", "b", "c"]}]}

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(live, "search", fake_search)
    monkeypatch.setattr(live, "claude_json", fake_claude)
    res = asyncio.run(live.build_viral())
    assert res["origin"] == "mixed" and len(res["cards"]) == 3
    assert res["cards"][0]["credit"] == "news.example" and res["cards"][0]["url"] == "https://news.example/0"
    assert all("crash" not in c["text"] for c in res["cards"])


def test_ai_moderation_can_flag_but_never_unflag(env, monkeypatch):
    client, clock, code, H = env
    calls = []

    async def fake_claude(system, user, schema, **kw):
        calls.append(user)
        if "Minh is ugly" in user:
            return {"allow": False, "category": "harassment", "reason": "insults a real person"}
        return {"allow": True, "category": "ok", "reason": ""}

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(live, "claude_json", fake_claude)
    join(client, code, "device-aaaa", name="Minh is ugly")
    clock.t += 9000
    join(client, code, "device-bbbb", name="fuck yeah")  # word filter flags it before AI is even asked
    teams = state(client, code, "host", headers=H)["teams"]
    assert teams[0]["name_status"] == "pending" and teams[0]["name_reason"] == "insults a real person"
    assert teams[1]["name_status"] == "pending" and teams[1]["name_reason"] == "word filter"
    assert not any("fuck yeah" in c for c in calls)
    assert all(t["name"] is None for t in state(client, code, "screen")["teams"])


def test_ai_moderation_failure_is_silent(env, monkeypatch):
    client, clock, code, H = env

    async def down(*a, **kw):
        return None

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(live, "claude_json", down)
    join(client, code, "device-aaaa", name="Bún Voyage")
    assert state(client, code, "screen")["teams"][0]["name"] == "Bún Voyage"


def test_claude_json_returns_none_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    assert asyncio.run(live.claude_json("s", "u", {"type": "object"})) is None
