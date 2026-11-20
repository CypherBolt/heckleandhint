"""Tier 3: live content. AI moderation, You.com search, "This Week in Saigon"
questions and Viral Drop cards.

Every external call is optional and fails SILENTLY to a local fallback:
- No ANTHROPIC_API_KEY (or the call fails, times out, or is refused) -> word filter / backup bank.
- No YDC_API_KEY (or search fails / takes longer than 6 s)            -> backup bank.
All calls happen on the backend only; the browser never talks to these services.
"""
import asyncio
import json
import os
import random
import re

from .filters import clean_text

MODEL = os.environ.get("HH_CLAUDE_MODEL", "claude-opus-5-5")
SEARCH_TIMEOUT_S = 6.0
YDC_URL = os.environ.get("YDC_SEARCH_URL", "https://ydc-index.io/v1/search")  # VERIFY against You.com docs

# Topics the live features must never touch (checked on AI output as a second safety net).
BANNED = re.compile(
    r"\b(death|dead|died|dies|die|kill|killed|killing|murder|suicide|crash|accident|victim|injur\w*|"
    r"crime|criminal|arrest\w*|police|court|trial|jail|prison|sentenced|drug\w*|fraud|scam|"
    r"politic\w*|election|government|minister|party|communist|protest\w*|war|military|"
    r"tử vong|chết|giết|tai nạn|bắt giữ|công an|tòa án|chính trị|chính phủ|bầu cử)\b",
    re.IGNORECASE,
)


def ai_enabled() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def search_enabled() -> bool:
    return bool(os.environ.get("YDC_API_KEY"))


def status() -> dict:
    return {"ai": ai_enabled(), "search": search_enabled()}


# ---------------------------------------------------------------- Claude (structured JSON)
_client = None


def _anthropic():
    global _client
    if _client is None:
        import anthropic

        _client = anthropic.AsyncAnthropic(max_retries=1)
    return _client


async def claude_json(system: str, user: str, schema: dict, *, effort: str = "low",
                      max_tokens: int = 4000, timeout: float = 20.0):
    """One structured-output call to Claude. Returns parsed JSON, or None on ANY problem."""
    if not ai_enabled():
        return None
    try:
        resp = await asyncio.wait_for(
            _anthropic().beta.messages.create(
                model=MODEL,
                max_tokens=max_tokens,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",  # if one model declines, the API retries on a fallback model
                output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
                system=system,
                messages=[{"role": "user", "content": user}],
            ),
            timeout,
        )
        if resp.stop_reason != "end_turn":  # refusal / max_tokens -> use the fallback path
            return None
        text = next((b.text for b in resp.content if b.type == "text"), None)
        return json.loads(text) if text else None
    except Exception as exc:  # network, auth, rate limit, timeout, bad JSON: all silent
        print(f"[heckle] Claude call skipped: {type(exc).__name__}")
        return None


# ---------------------------------------------------------------- AI moderation
MOD_SCHEMA = {
    "type": "object",
    "properties": {
        "allow": {"type": "boolean"},
        "category": {"type": "string", "enum": ["ok", "hate", "sexual", "harassment", "personal_data",
                                                 "violence", "self_harm", "other"]},
        "reason": {"type": "string"},
    },
    "required": ["allow", "category", "reason"],
    "additionalProperties": False,
}

MOD_SYSTEM = (
    "You moderate short texts that pub-quiz players type on their phones in a Ho Chi Minh City bar. "
    "Texts may be Vietnamese, English or a mix, including slang and teencode. Approved texts are shown "
    "on a big TV screen in a public bar. House rule: joke about choices, not people.\n"
    "Allow: puns, playful trash talk about teams or the host's jokes, mild swearing used for emphasis, food jokes.\n"
    "Block: slurs or hate, sexual content, harassment or insults aimed at a real or private person, "
    "personal data (phone numbers, emails, addresses, full names of private people), threats or violence, "
    "self-harm, and disguised versions of these (spacing, leetspeak, accents removed).\n"
    "reason: at most 8 words, English, for the host."
)


async def moderate(text: str, limit: int, kind: str = "text") -> dict:
    """Word filter always runs. AI (if available) can only ADD a flag, never remove one."""
    base = clean_text(text, limit)
    out = {**base, "mod_source": "filter", "mod_reason": "word filter" if base["flagged"] else ""}
    if base["flagged"] or not base["text"] or not ai_enabled():
        return out
    verdict = await claude_json(MOD_SYSTEM, f"Kind: {kind}\nText: {base['text']}", MOD_SCHEMA,
                                effort="low", max_tokens=1500, timeout=6.0)
    if verdict is None:
        return out  # silent fallback to the word filter
    out["mod_source"] = "ai"
    if not verdict.get("allow", True):
        out["flagged"] = True
        out["mod_reason"] = str(verdict.get("reason") or verdict.get("category") or "AI flag")[:60]
    return out


# ---------------------------------------------------------------- You.com search
def _parse_results(data) -> list[dict]:
    """Accept the shapes You.com has used: v1 {results:{web,news}}, legacy {hits}, news {news:{results}}."""
    items = []
    if isinstance(data, dict):
        res = data.get("results")
        if isinstance(res, dict):
            items += res.get("news") or []
            items += res.get("web") or []
        elif isinstance(res, list):
            items += res
        items += data.get("hits") or []
        news = data.get("news")
        if isinstance(news, dict):
            items += news.get("results") or []
    out, seen = [], set()
    for it in items:
        if not isinstance(it, dict):
            continue
        url = str(it.get("url") or "")
        title = str(it.get("title") or "").strip()
        if not url.startswith("http") or not title or url in seen:
            continue
        seen.add(url)
        snippets = it.get("snippets") or []
        desc = str(it.get("description") or (snippets[0] if snippets else "") or "").strip()
        source = str(it.get("source_name") or it.get("source") or re.sub(r"^https?://(www\.)?([^/]+).*", r"\2", url))
        out.append({"title": title[:200], "url": url[:500], "snippet": desc[:400], "source": source[:80],
                    "age": str(it.get("page_age") or it.get("age") or "")[:40]})
    return out


async def search(query: str, count: int = 8) -> list[dict] | None:
    """You.com web+news search. None = unavailable (no key, error, or > 6 s)."""
    key = os.environ.get("YDC_API_KEY")
    if not key:
        return None
    try:
        import httpx2 as httpx

        async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT_S) as client:
            r = await asyncio.wait_for(
                client.get(YDC_URL, params={"query": query, "count": count, "freshness": "week", "country": "VN"},
                           headers={"X-API-Key": key}),
                SEARCH_TIMEOUT_S,
            )
        if r.status_code != 200:
            print(f"[heckle] You.com search HTTP {r.status_code}; using backup bank")
            return None
        return _parse_results(r.json())
    except Exception as exc:
        print(f"[heckle] You.com search skipped: {type(exc).__name__}")
        return None


async def gather_news(queries: list[str]) -> list[dict] | None:
    results = await asyncio.gather(*(search(q) for q in queries))
    if all(r is None for r in results):
        return None
    merged, seen = [], set()
    for lst in results:
        for it in lst or []:
            if it["url"] not in seen and not BANNED.search(f"{it['title']} {it['snippet']}"):
                seen.add(it["url"])
                merged.append(it)
    return merged[:24]


# ---------------------------------------------------------------- backup banks (no network needed)
def _bq(en, vi, opts, correct, src_title, src_url, setup_en, setup_vi, punch_en, punch_vi):
    return {"type": "quiz", "text": {"en": en, "vi": vi},
            "options": [{"en": a, "vi": b} for a, b in opts], "correct": correct, "time_limit": 20,
            "setup": {"en": setup_en, "vi": setup_vi}, "punchline": {"en": punch_en, "vi": punch_vi},
            "notes": "Backup bank (no live search available).", "source": {"title": src_title, "url": src_url}}


BACKUP_WEEKLY = [  # VI-CHECK: native speaker review
    _bq("Saigon's Metro Line 1 runs from Bến Thành to which area?", "Tuyến Metro số 1 Sài Gòn chạy từ Bến Thành đến khu vực nào?",
        [("Suối Tiên", "Suối Tiên"), ("Cần Giờ", "Cần Giờ"), ("Tân Sơn Nhất", "Tân Sơn Nhất"), ("Vũng Tàu", "Vũng Tàu")], 0,
        "Ho Chi Minh City Metro (Wikipedia)", "https://en.wikipedia.org/wiki/Ho_Chi_Minh_City_Metro",
        "The metro finally runs. Saigon traffic did not get the memo.", "Metro chạy rồi. Kẹt xe Sài Gòn chưa nhận được thông báo.",
        "Vũng Tàu pickers: that's a weekend trip, not a metro stop.", "Ai chọn Vũng Tàu: đó là chuyến đi cuối tuần, không phải ga metro."),
    _bq("Which street is famous as Saigon's walking street?", "Con đường nào nổi tiếng là phố đi bộ của Sài Gòn?",
        [("Nguyễn Huệ", "Nguyễn Huệ"), ("Lê Lợi", "Lê Lợi"), ("Hai Bà Trưng", "Hai Bà Trưng"), ("Võ Văn Kiệt", "Võ Văn Kiệt")], 0,
        "Nguyễn Huệ Boulevard (Wikipedia)", "https://en.wikipedia.org/wiki/Nguy%E1%BB%85n_Hu%E1%BB%87_Boulevard",
        "Nguyễn Huệ: the only street in Saigon where walking is the fastest option.", "Nguyễn Huệ: con đường duy nhất ở Sài Gòn mà đi bộ là nhanh nhất.",
        "Võ Văn Kiệt pickers: please don't walk on that one.", "Ai chọn Võ Văn Kiệt: làm ơn đừng đi bộ trên đường đó."),
    _bq("Bùi Viện is best known for…?", "Bùi Viện nổi tiếng nhất vì…?",
        [("Nightlife and backpacker bars", "Quán bar và khách du lịch ba lô"), ("Silk markets", "Chợ lụa"),
         ("Temples", "Đền chùa"), ("Car dealerships", "Đại lý ô tô")], 0,
        "Bùi Viện Street (Wikipedia)", "https://en.wikipedia.org/wiki/B%C3%B9i_Vi%E1%BB%87n_Street",
        "Bùi Viện: where good decisions go to have a quick beer.", "Bùi Viện: nơi những quyết định đúng đắn ghé uống một lon.",  # VI-CHECK
        "Car dealership team: you've been to a very different Bùi Viện.", "Đội đại lý ô tô: các bạn đi nhầm Bùi Viện khác rồi."),
    _bq("The Saigon Central Post Office is often credited to the firm of which engineer?",
        "Bưu điện Trung tâm Sài Gòn thường được cho là gắn với công ty của kỹ sư nào?",
        [("Gustave Eiffel", "Gustave Eiffel"), ("Le Corbusier", "Le Corbusier"), ("Antoni Gaudí", "Antoni Gaudí"), ("Frank Gehry", "Frank Gehry")], 0,
        "Saigon Central Post Office (Wikipedia)", "https://en.wikipedia.org/wiki/Saigon_Central_Post_Office",
        "Often credited to Eiffel's firm. Yes, the tower guy also did your mail.", "Thường được gắn với công ty của Eiffel. Đúng, ông tháp Eiffel cũng lo luôn thư từ.",
        "Gaudí team: the post office is not melting, it's just humid.", "Đội Gaudí: bưu điện không chảy ra đâu, chỉ là trời ẩm thôi."),
    _bq("Which dish is Saigon's broken rice?", "Món nào là 'cơm tấm' của Sài Gòn?",
        [("Cơm tấm", "Cơm tấm"), ("Cơm chiên", "Cơm chiên"), ("Cơm gà", "Cơm gà"), ("Cơm niêu", "Cơm niêu")], 0,
        "Cơm tấm (Wikipedia)", "https://en.wikipedia.org/wiki/C%C6%A1m_t%E1%BA%A5m",
        "Broken rice: proof that Saigon can turn anything broken into breakfast.", "Cơm tấm: bằng chứng Sài Gòn biến cái gì gãy cũng thành bữa sáng.",
        "Fried rice team: close, it's broken in a different way.", "Đội cơm chiên: gần đúng, nó 'gãy' kiểu khác."),
    _bq("Landmark 81 stands in which district?", "Landmark 81 nằm ở quận nào?",
        [("Bình Thạnh", "Bình Thạnh"), ("District 7", "Quận 7"), ("Thủ Đức", "Thủ Đức"), ("Gò Vấp", "Gò Vấp")], 0,
        "Landmark 81 (Wikipedia)", "https://en.wikipedia.org/wiki/Landmark_81",
        "Bình Thạnh: home of the tallest building and the longest lift queue.", "Bình Thạnh: nhà của toà nhà cao nhất và hàng chờ thang máy dài nhất.",
        "District 7 team: you can see it from there. That's not the same thing.", "Đội Quận 7: từ đó nhìn thấy được. Nhưng không phải vậy đâu."),
    _bq("Mid-Autumn Festival kids traditionally carry…?", "Trẻ em thường mang gì trong dịp Tết Trung Thu?",
        [("Star lanterns", "Lồng đèn ông sao"), ("Umbrellas", "Dù"), ("Kites", "Diều"), ("Flags", "Cờ")], 0,
        "Mid-Autumn Festival (Wikipedia)", "https://en.wikipedia.org/wiki/Mid-Autumn_Festival",
        "Star lanterns: the original phone flashlight.", "Lồng đèn ông sao: đèn pin điện thoại thời xưa.",
        "Umbrella team: that's every other night in Saigon.", "Đội dù: đó là mọi buổi tối khác ở Sài Gòn."),
    _bq("Chợ Lớn is known as Saigon's…?", "Chợ Lớn được biết đến là…?",
        [("Chinatown", "Khu người Hoa"), ("Japantown", "Phố Nhật"), ("Little Italy", "Tiểu Ý"), ("Airport district", "Khu sân bay")], 0,
        "Chợ Lớn (Wikipedia)", "https://en.wikipedia.org/wiki/Ch%E1%BB%A3_L%E1%BB%9Bn",
        "Chợ Lớn: where your grandma's dim sum recommendations come from.", "Chợ Lớn: nơi bà ngoại bạn giới thiệu dimsum.",
        "Little Italy team: that's just a pizza place on Pasteur.", "Đội Tiểu Ý: đó chỉ là tiệm pizza trên đường Pasteur."),
    _bq("What is 'xe ôm'?", "'Xe ôm' là gì?",
        [("A motorbike taxi", "Xe máy chở khách"), ("A rice cooker", "Nồi cơm điện"), ("A street dance", "Một điệu nhảy đường phố"), ("A hug festival", "Lễ hội ôm")], 0,
        "Motorcycle taxi (Wikipedia)", "https://en.wikipedia.org/wiki/Motorcycle_taxi",
        "Xe ôm literally means 'hug vehicle'. Hold on tight, it's not optional.", "Xe ôm nghĩa là xe phải ôm. Ôm chặt, không có lựa chọn khác.",  # VI-CHECK
        "Hug festival team: technically, every ride.", "Đội lễ hội ôm: nói đúng ra thì chuyến nào cũng vậy."),
    _bq("Which Saigon market is the city's biggest wholesale food market?", "Chợ nào là chợ đầu mối nông sản lớn nhất Sài Gòn?",
        [("Bình Điền", "Bình Điền"), ("Bến Thành", "Bến Thành"), ("Tân Định", "Tân Định"), ("Hồ Thị Kỷ", "Hồ Thị Kỷ")], 0,
        "Ho Chi Minh City (Wikipedia)", "https://en.wikipedia.org/wiki/Ho_Chi_Minh_City",  # VERIFY: Bình Điền fact
        "Bình Điền: open while you sleep, so you can eat while you're awake.", "Bình Điền: mở cửa khi bạn ngủ để bạn ăn khi bạn thức.",
        "Bến Thành team: that's where the tourists go, not the restaurants.", "Đội Bến Thành: đó là chỗ của khách du lịch, không phải nhà hàng."),
]

BACKUP_VIRAL = [  # Generic Saigon internet-culture moments, credited honestly (no invented creators).
    {"title": "The 5-minute flood", "text": "It rains for five minutes. Half the city's street turns into a river and someone rows past in a plastic tub.",
     "credit": "Recurring Saigon rainy-season meme", "url": "",
     "angles": ["Rank the city's rain-coping strategies from 'poncho' to 'become a boat'.",
                "Ask the room who has ever arrived somewhere 'slightly damp'.",
                "Treat the tub-rower as an Olympic sport and commentate."]},
    {"title": "Grab driver calls 7 times", "text": "Driver: 'Em ơi, em đứng đâu?' You: pinned location, photo, landmark, blood type. Driver: calls again.",
     "credit": "Everyday ride-hailing meme", "url": "",
     "angles": ["Act out the call, play both sides.", "Ask which team has the best 'where are you' answer.",
                "Compare it to a hostage negotiation."]},
    {"title": "Trà chanh sidewalk summit", "text": "Eight friends on tiny plastic stools solving the world's problems over 10k lime tea until 1 a.m.",
     "credit": "Saigon street-café culture trend", "url": "",
     "angles": ["Survey: who has the best 'small stool' posture?", "Pitch the stools as a fitness trend.",
                "Ask the room for one problem the stool summit actually solved."]},
    {"title": "The bánh mì price check", "text": "Same bánh mì, same cart, three different prices depending on how foreign your accent sounds today.",
     "credit": "Popular expat-life joke format", "url": "",
     "angles": ["Do the accent sliding scale, gently, about yourself.", "Ask locals in the room for the 'real' price.",
                "Make the bánh mì cart a stock market."]},
    {"title": "Helmet fashion week", "text": "Pastel helmets with cat ears, duck bills and tiny horns: Saigon's real runway is at the red light.",
     "credit": "Saigon helmet-style trend", "url": "",
     "angles": ["Rate the room's imaginary helmets.", "Commentate a red light like a fashion show.",
                "Ask which team would wear the duck bill."]},
    {"title": "Sunday family motorbike", "text": "Dad, mum, two kids, a dog and a durian on one scooter, everyone calm.",
     "credit": "Classic Vietnam traffic photo meme", "url": "",
     "angles": ["Ask for the room's personal scooter record.", "Treat it as a physics lesson.",
                "Imagine the durian's point of view."]},
    {"title": "Karaoke at 9 p.m. sharp", "text": "The neighbour's karaoke starts exactly when your baby falls asleep. Today's song: the same ballad, 14 times.",
     "credit": "Neighbourhood karaoke meme", "url": "",
     "angles": ["Ask which ballad haunts each team.", "Sing one line badly (optional, at your own risk).",
                "Score the neighbour like a reality-show judge."]},
    {"title": "Coffee before coffee", "text": "Ordering a cà phê sữa đá to wake up enough to go and get your real coffee.",
     "credit": "Vietnamese coffee culture joke", "url": "",
     "angles": ["Count the room's coffees today.", "Invent a coffee-before-coffee menu.",
                "Ask who is drinking coffee right now. In a bar."]},
]


# ---------------------------------------------------------------- This Week in Saigon
WEEKLY_QUERIES = [
    "Ho Chi Minh City news this week food festival",
    "Saigon events this week culture music",
    "Ho Chi Minh City this week new opening lifestyle",
    "Vietnam trending this week sports entertainment",
]

OPT = {"type": "object", "properties": {"en": {"type": "string"}, "vi": {"type": "string"}},
       "required": ["en", "vi"], "additionalProperties": False}
WEEKLY_SCHEMA = {
    "type": "object",
    "properties": {"questions": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "text": OPT, "options": {"type": "array", "items": OPT}, "correct": {"type": "integer"},
            "setup": OPT, "punchline": OPT, "source_index": {"type": "integer"},
        },
        "required": ["text", "options", "correct", "setup", "punchline", "source_index"],
        "additionalProperties": False,
    }}},
    "required": ["questions"], "additionalProperties": False,
}
WEEKLY_SYSTEM = (
    "You write questions for a light-hearted bilingual (English + Vietnamese) pub quiz in a Ho Chi Minh City bar, "
    "hosted by a stand-up comedian. Write exactly 6 multiple-choice questions about THIS WEEK in Saigon, using ONLY "
    "facts stated in the numbered search results provided. Each question must cite the result it came from via "
    "source_index. Strictly avoid: deaths, accidents, crime, police or courts, politics or government, war, "
    "disasters with victims, and any private (non-public) person. Prefer food, events, openings, culture, sport, "
    "weather quirks and fun numbers. Exactly 4 options, one correct (correct = its 0-based index), plausible but "
    "funny wrong options. setup: one line the comedian says before revealing the answer; punchline: a kind joke "
    "about the people who picked wrong. Keep each field under 160 characters. Natural Vietnamese with full accents."
)


def _valid_q(q, n_sources) -> bool:
    try:
        if len(q["options"]) != 4 or q["correct"] not in (0, 1, 2, 3):
            return False
        if not (0 <= q["source_index"] < n_sources):
            return False
        blob = json.dumps(q, ensure_ascii=False)
        return not BANNED.search(blob) and all(o["en"].strip() and o["vi"].strip() for o in q["options"])
    except (KeyError, TypeError, AttributeError):
        return False


async def build_weekly() -> dict:
    """Returns {"origin": "live"|"backup", "questions": [...6...], "note": str}."""
    news = await gather_news(WEEKLY_QUERIES)
    if news and ai_enabled():
        listing = "\n".join(f"[{i}] {n['title']} ({n['source']}, {n['age']}): {n['snippet']}" for i, n in enumerate(news))
        data = await claude_json(WEEKLY_SYSTEM, f"Search results from this week:\n{listing}", WEEKLY_SCHEMA,
                                 effort="medium", max_tokens=12000, timeout=45.0)
        good = []
        for q in (data or {}).get("questions", []):
            if _valid_q(q, len(news)):
                src = news[q["source_index"]]
                good.append({"type": "quiz", "text": q["text"], "options": q["options"], "correct": q["correct"],
                             "time_limit": 20, "setup": q["setup"], "punchline": q["punchline"],
                             "notes": f"Live: {src['title']} ({src['source']})",
                             "source": {"title": src["title"], "url": src["url"]}})
        if len(good) >= 3:
            return {"origin": "live", "questions": good[:6], "note": ""}
    picks = random.sample(BACKUP_WEEKLY, 6)
    return {"origin": "backup", "questions": [dict(q) for q in picks],
            "note": "no_live" if not news else "ai_unavailable"}


# ---------------------------------------------------------------- Viral Drop
VIRAL_QUERIES = ["viral Vietnam this week", "trending Saigon social media this week", "Vietnam meme trending"]
VIRAL_SCHEMA = {
    "type": "object",
    "properties": {"cards": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "title": {"type": "string"}, "text": {"type": "string"}, "source_index": {"type": "integer"},
            "angles": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["title", "text", "source_index", "angles"], "additionalProperties": False,
    }}},
    "required": ["cards"], "additionalProperties": False,
}
VIRAL_SYSTEM = (
    "You pick viral posts / memes for a live comedy pub quiz in Saigon. From the numbered search results, choose "
    "exactly 3 light, harmless viral moments. For each: a short title (max 6 words), a text-only description of the "
    "post (max 140 characters, no images, do not quote anyone's full words, no private people's names), the "
    "source_index it came from, and exactly 3 private joke angles for the comedian (max 100 characters each) that "
    "joke about situations and choices, never about a person's looks, identity or misfortune. Skip anything about "
    "deaths, accidents, crime, politics, war, or private individuals."
)


async def build_viral() -> dict:
    news = await gather_news(VIRAL_QUERIES)
    cards = []
    if news and ai_enabled():
        listing = "\n".join(f"[{i}] {n['title']} ({n['source']}): {n['snippet']}" for i, n in enumerate(news))
        data = await claude_json(VIRAL_SYSTEM, f"Search results:\n{listing}", VIRAL_SCHEMA,
                                 effort="medium", max_tokens=8000, timeout=40.0)
        for c in (data or {}).get("cards", []):
            try:
                if not (0 <= c["source_index"] < len(news)) or len(c["angles"]) < 3:
                    continue
                if BANNED.search(json.dumps(c, ensure_ascii=False)):
                    continue
                src = news[c["source_index"]]
                cards.append({"title": c["title"][:60], "text": c["text"][:160],
                              "credit": src["source"], "url": src["url"],
                              "angles": [a[:120] for a in c["angles"][:3]], "origin": "live"})
            except (KeyError, TypeError):
                continue
    origin = "live" if len(cards) >= 3 else ("mixed" if cards else "backup")
    if len(cards) < 3:
        used = {c["title"] for c in cards}
        pool = [dict(c, origin="backup") for c in BACKUP_VIRAL if c["title"] not in used]
        cards += random.sample(pool, 3 - len(cards))
    return {"origin": origin, "cards": cards[:3]}
