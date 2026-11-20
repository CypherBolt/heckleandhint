#speech to ship
# heckle & hint

## Heckle & Hint 🎤

A bilingual (VI/EN) pub quiz for Saigon bars, run one-handed by a stand-up comedian.
**The quiz writes the setup. The comedian delivers the punchline.**

Stack: React (Vite) + FastAPI + MongoDB. Polling only (every 1.5 s), no WebSockets, no paid services.

## Quick start (no Node needed: the frontend is already built)
- **Mac / Linux:** open a terminal in this folder and run `./run.sh`
- **Windows:** double-click `run.bat`

Then open http://localhost:8000. Needs Python 3.10 or newer.

## Run it by hand (one process serves everything)

```bash
pip install fastapi uvicorn motor pymongo mongomock-motor httpx pytest
cd frontend && npm install && npm run build && cd ..
python3 -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
```

Open http://localhost:8000 → **Host a night**. Phones on the same Wi-Fi join with
`http://<your-laptop-ip>:8000/join/CODE` (the TV's QR code points there).

**Database:** set `MONGO_URL=mongodb://localhost:27017` to use real MongoDB. Without it (or if
Mongo is unreachable) the server silently uses an in-memory Mongo emulator: fine for demos,
but rooms vanish on restart.

**Dev mode with hot reload:** run uvicorn as above plus `cd frontend && npm run dev` (port 5173,
proxies `/api` to 8000).

## Screens
| URL | Who |
|---|---|
| `/` | Landing: Host a night / Join with code |
| `/host/CODE?key=…` | Host console (comedian's phone). Key is saved to localStorage, then hidden from the URL |
| `/screen/CODE` | Big screen (16:9 TV). Double-click for full screen |
| `/join/CODE` → `/play/CODE` | Player (one phone per team) |
| `/recap/CODE` | Public recap (top 3) |
| `/host/CODE/report` | Set report (Tier 1: per-question breakdown) |

## What's in each tier
**Tier 1 (core loop):** join with pun names, Kahoot-style questions, server timers, scoring with streaks,
private host Riff Radar, moderation + Blackout, demo crowd.

**Tier 2 (comedy layer):**
- Riff Fuel chips after lock: most popular, lone wolf, split room, confidently wrong, fastest wrong, rivals.
- Write-in questions: duplicates grouped, host approves up to 6, phones vote. +100 laugh per approved answer, +300 winner.
- Phone action bar: LAUGH (hold, max 4/s per phone), GROAN, HECKLE. Vertical laugh meter on the TV
  ("Polite" → "CALL A DOCTOR"). Every riff, heckle, roast and spotlight is recorded as a *bit* with its laughs.
- Heckle queue: "Show on screen" for 8 s, +100 laugh.
- Team actions: +200 Style Points (with Undo), Roast Card (Mild/Spicy only: phone turns red, TV shakes),
  Spotlight (mic-ready only).
- ⭐ Star button saves a moment with a note.
- Sound board synthesised with Web Audio, played by the TV only (tap "Tap to start" on the TV once).
- Question editor (upcoming questions only; the finale is always last).
- Finale: wager 0–100% (bottom 3 win double) → final question → awards → podium → Follow card on every phone.
- `/recap/CODE` (top 3, best heckle, funniest answer, awards) and `/host/CODE/report` (bits ranked, keep top 5,
  rework bottom 3, stars, Copy / Download Markdown).

## Tier 3: live content (optional keys)
Everything works with **no keys**: the word filter and built-in backup banks take over silently.
Set these environment variables before starting the server to switch the live features on:

| Variable | Turns on |
|---|---|
| `ANTHROPIC_API_KEY` | AI moderation of all player text (can only *add* flags, never remove the word filter's), AI-written "This Week in Saigon" questions and Viral Drop cards (model `claude-opus-5-5`, structured JSON, server-side refusal fallback) |
| `YDC_API_KEY` | You.com search (backend only, 6 s timeout) feeding those two features |
| `YDC_SEARCH_URL` | Optional: override the You.com endpoint (default `https://ydc-index.io/v1/search`) |

- **This Week in Saigon:** host taps *Write 6 questions from this week* → drafts with a source link each → Approve
  (joins the quiz before the finale) or Reject. Topics about deaths, crime, politics or private people are blocked
  twice: in the instructions to the model, and by a server-side keyword filter on what comes back.
- **Viral Drop:** host fetches 3 text-only, credited cards (with 3 *private* joke angles each), sends them between
  questions → phones vote (15 s) → 60 s riff with the laugh meter → the room rates the riff (1–5 ⭐). The riff is saved
  as a bit with its laughs and rating in the set report.

## Design & UI libraries
Look: dark neon bar poster: square corners, hard 4 px shadows, faint film grain, Kahoot answer colours.
Library picks follow Emil Kowalski's curated list (pick-ui-library skill), all restyled to that look
(no Tailwind, so shadcn / Aceternity / Magic UI were used as *patterns*, not installed):

| Where | Library | Why |
|---|---|---|
| Error / confirm pop-ups, Style Points **Undo** | Sonner | swipeable, stacks, pauses when the tab is hidden |
| Heckle, Star, team-action and quick-action sheets | Vaul | real bottom sheets: swipe down to close, focus trapped |
| Host quick actions (⌘K or the ⌕ button) | cmdk | one-handed: type a team name → act |
| Scores, countdowns, points | NumberFlow | digits roll instead of jumping |
| Host tabs, switches, roast / wager / mascot pickers | Base UI | accessible primitives (keyboard, screen reader) |
| TV scoreboard re-ordering, team tiles, awards, podium | motion | spring layout animations |
| Confetti on correct answers, write-in wins, podium | canvas-confetti | Magic UI's confetti engine |
| Fun-fact ticker in the TV lobby | CSS marquee | Magic UI pattern, zero JS |

Motion follows the same guide: strong ease-out curves, presses respond in about 120 ms, exits are faster than
entrances, and everything respects "reduce motion". Each page loads only its own code (phones don't download TV code).

## Demo for judges
Host console → **Load demo data** (8 teams) → **Simulate crowd** → tap NEXT repeatedly.
Demo teams answer 2–6 s after each question opens (~60% correct), write in answers, vote, wager,
and laugh during riffs so the laugh meter moves. On the TV, tap "Tap to start" once to enable sounds.

## Tests
```bash
cd backend && python3 -m pytest -q
```

## Where things live
- `backend/app/main.py`: rooms, phase machine, scoring, role-filtered state, host actions
- `backend/app/filters.py`: EN+VI bad-words list, phone/email/@handle stripping
- `backend/app/seed.py`: 14 bilingual questions (12 trivia + 2 polls) and demo teams
- `frontend/src/i18n.jsx`: every UI string (en + vi), rotating microcopy, pun names
- Search for `VI-CHECK` to find Vietnamese lines a native speaker should review
