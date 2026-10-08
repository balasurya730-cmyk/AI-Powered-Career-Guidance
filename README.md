# AI Learning Planner & Career Advisor

> **Reviewed & polished.** See [CHANGES.md](./CHANGES.md) for what was checked, tested, and fixed in this pass — including an important security note about your Gemini API key.


A full-stack web app that helps students pick a suitable career and get a
personalized, AI-generated learning plan — powered by Google's Gemini API.

Built with:
- **Frontend:** HTML, CSS, vanilla JavaScript
- **Backend:** FastAPI (Python)
- **Database:** SQLite
- **AI:** Google Gemini API

---

## 1. Features

- **Global Career Profiles (A-Z Careers)** — dynamically generated, comprehensive global career profiles using AI.
- **Student Profile** — education, skills, interests, daily study hours, and an optional target career goal.
- **AI Career Advisor** — asks contextual questions to recommend the top 5 matching careers for undecided students.
- **Skill Gap Analyzer** — identifies missing skills for a selected career and suggests specific free/low-cost courses and certifications to bridge the gap.
- **AI Learning Planner** — generates a personalized daily plan, weekly schedule, skills checklist, resources, and practice projects.
- **Phased Roadmap & Milestones** — automatically breaks down long-term goals into multi-month curriculums, gated by AI-proctored technical assessments for each phase.
- **Gamification & Leaderboard** — keeps students engaged with global leaderboards, badges, streaks, and a friends activity feed.
- **Certification Module** — students earn a cryptographic "Trailhead Certified" certificate of completion after passing all roadmap phases.
- **Mock Interviews** — AI-powered technical mock interviews tailored to the student's career track with detailed grading.
- **Peer Networking & Group Chat** — find peers with similar goals, join global study rooms, and participate in direct 1-on-1 AI-moderated chat.
- **Video Meet** — virtual study rooms via integrated WebRTC logic.
- **Robust AI Fallbacks** — handles AI provider rate limits seamlessly by falling back to mock generators, preventing app downtime.

---

## 2. Project structure

```
ai_learning_planner/
├── backend/
│   ├── main.py              # FastAPI app + all API routes
│   ├── database.py          # SQLite connection + table creation
│   ├── models.py             # Pydantic request/response schemas
│   ├── auth_utils.py         # Password hashing + JWT helpers
│   ├── gemini_service.py     # Gemini API calls (career advice + learning plans)
│   ├── seed_data.py          # Optional: creates one demo login for testing
│   ├── requirements.txt
│   └── .env.example          # Copy to .env and fill in your Gemini API key
├── frontend/
│   ├── index.html            # Home
│   ├── register.html
│   ├── login.html
│   ├── profile.html          # Student Profile
│   ├── career-advisor.html   # AI Career Advisor
│   ├── learning-planner.html # AI Learning Planner
│   ├── dashboard.html        # Dashboard + Progress Tracker
│   ├── chat.html              # AI Chat (free-form Q&A)
│   ├── css/style.css
│   └── js/
│       ├── api.js            # Shared fetch wrapper + auth/session helpers
│       ├── auth.js            # Register/login form logic
│       ├── profile.js
│       ├── career.js
│       ├── planner.js
│       └── dashboard.js
├── database/
│   └── schema.sql             # Reference copy of the schema (auto-created by database.py)
└── README.md
```

---

## 3. Prerequisites

- Python 3.10 or newer
- A free Gemini API key: https://aistudio.google.com/app/apikey

---

## 4. Installation guide

**Step 1 — Get the code onto your machine and open a terminal in the project's root folder** (the folder containing `backend/`, `frontend/`, `database/`).

**Step 2 — Create a virtual environment (recommended)**

```bash
python -m venv venv

# Activate it:
# Windows:
venv\Scripts\activate
# macOS / Linux:
source venv/bin/activate
```

**Step 3 — Install backend dependencies**

```bash
cd backend
pip install -r requirements.txt
```

**Step 4 — Configure your environment variables**

```bash
# still inside backend/
cp .env.example .env      # Windows: copy .env.example .env
```

Open `.env` and fill in:

```
GEMINI_API_KEY=your_real_gemini_api_key
JWT_SECRET_KEY=any_long_random_string
JWT_EXPIRE_MINUTES=1440
```

**Step 5 — Run the server**

```bash
uvicorn main:app --reload --port 8000
```

You should see:
```
[database] SQLite ready at .../backend/learning_planner.db
Uvicorn running on http://127.0.0.1:8000
```

**Step 6 — Open the app**

Go to **http://127.0.0.1:8000** in your browser. The FastAPI server serves
both the API (`/api/...`) and the frontend pages from a single port, so
there's nothing else to start.

**Step 7 (optional) — Load sample/demo data**

In a second terminal (with the venv activated, inside `backend/`):

```bash
python seed_data.py
```

This creates a demo login you can use immediately:
```
email:    demo@student.com
password: demo1234
```

---

## 5. How the app flows

1. **Home** → click **Get Started** → **Register**
2. Fill in your **Student Profile** (career goal is optional)
3. If you left career goal blank → **AI Career Advisor** asks 3 quick
   questions, then shows your **top 5 career matches** — pick one
4. **AI Learning Planner** generates your daily/weekly/monthly plan,
   skills list, free resources, and a practice project
5. **Dashboard** shows everything together, with a checklist you can tick
   off — your progress percentage updates automatically

---

## 6. API reference

All endpoints are prefixed with `/api`. Except register/login, every route
requires an `Authorization: Bearer <token>` header (the frontend handles
this automatically once you're logged in).

| Method | Endpoint                        | Purpose                                   |
|--------|----------------------------------|--------------------------------------------|
| POST   | `/api/register`                 | Create an account, returns a session token |
| POST   | `/api/login`                    | Log in, returns a session token            |
| POST   | `/api/profile`                  | Create/update your student profile         |
| GET    | `/api/profile`                  | Get your saved profile                     |
| POST   | `/api/career/recommend`         | Get 3 AI-recommended careers               |
| GET    | `/api/career/options`           | Get your last set of recommendations       |
| POST   | `/api/career/select`            | Choose one recommended career              |
| POST   | `/api/learning-plan/generate`   | Generate an AI learning plan               |
| POST   | `/api/progress/update`          | Mark a task complete/incomplete            |
| GET    | `/api/dashboard`                | Get everything for the dashboard           |
| POST   | `/api/chat`                     | Free-form Q&A with the AI, with optional session conversation history |

Interactive API docs (Swagger UI) are also available automatically at
**http://127.0.0.1:8000/docs** once the server is running.

---

## 8. End-to-end smoke test

Run the backend from `backend/` (see step 5 above), then in a second
terminal, from the project root, with your venv activated:

```bash
cd tests
pip install playwright && playwright install chromium   # one-time setup

# point it at your running server:
export APP_BASE_URL=http://127.0.0.1:8000     # Windows (PowerShell): $env:APP_BASE_URL='http://127.0.0.1:8000'
python playwright_smoke.py
```

The smoke test logs in with the seeded demo account (run `python
backend/seed_data.py` first if you haven't):

- email: `demo@student.com`
- password: `demo1234`

There's also `tests/e2e_test.py`, which drives the raw API (register,
profile, career advisor, skill gap, learning plan, dashboard, phases, chat,
etc.) for several simulated users without needing a browser — run it the
same way, with the server already running:

```bash
python tests/e2e_test.py
```

---

## 9. Notes on the AI integration

- The app can call several AI providers (Gemini, OpenRouter, NVIDIA, Cohere,
  Z.AI, and others), configurable per feature via the `PROVIDER_*` variables
  in `.env` — see `.env.example` for the full list.
- Each AI call is prompted to reply in strict JSON, which is parsed directly
  into the database and API responses; markdown code fences around the
  response are stripped automatically if present.
- **The app works even with no API keys configured.** If every configured
  provider is missing, out of quota, or unreachable, every AI-backed feature
  (career advisor, learning plan, skill gap, chat, mock interview, project
  review, and more) falls back to a clearly-labeled mock response instead of
  failing — so you can develop and demo the whole app offline. Fill in real
  keys in `.env` when you want live AI-generated content instead.

---

## 10. Security notes

- Passwords are hashed with bcrypt (via `passlib`) — never stored in plain text.
- Login sessions use signed JWTs with an expiry (`JWT_EXPIRE_MINUTES`).
- `JWT_SECRET_KEY` should be a long, random string in any real deployment —
  never commit your real `.env` file to version control (it's already in
  `.gitignore`).
- CORS is wide open (`allow_origins=["*"]`) for easy local development.
  Restrict this in `backend/main.py` before deploying publicly.
- If you ever share this project as a zip (for review, backup, etc.),
  double check `backend/.env` isn't included — only `.env.example` should
  be. If a real `.env` ever does get shared or committed by mistake, treat
  every key in it as compromised and rotate them at each provider's
  dashboard.

---

## 11. Troubleshooting

- **AI features return generic/mock-looking content** — this is expected
  fallback behavior when no AI provider succeeds (see section 9). Check
  `backend/.env` has a real, non-placeholder key for at least one provider,
  and that the corresponding `PROVIDER_*` variable points to it.
- **401 errors / getting logged out unexpectedly** — your session token
  expired (default 24 hours); just log in again.
- **Port already in use** — run on a different port:
  `uvicorn main:app --reload --port 8001` (then open that port in your browser).
