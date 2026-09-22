# Tally Financial Intelligence

A full-stack financial dashboard and AI chatbot that sits on top of **Tally Prime** and turns raw accounting data into readable reports, live dashboards, and natural-language answers.

Instead of opening Tally and digging through menus, a user can just ask *"what's our net profit this month?"* or *"who owes us the most money?"* and get a straight answer, pulled live from the company's actual books.

---

## Why this exists

Tally is where most Indian SMBs keep their real accounting data, but it's a desktop tool nobody outside the accounts team ever looks at it, and there's no easy way to check numbers from a phone or share a quick summary with a manager.

This project bridges that gap:

- A **FastAPI backend** talks to Tally's XML API, pulls the reports, and cleans them into simple JSON.
- A **React dashboard** displays that data as cards, tables, and charts.
- A **Gemini-powered chatbot** lets anyone ask financial questions in plain English and get an answer built from a real Tally report, not a guess.

Every number shown anywhere in the app is fetched live from Tally at request time. Nothing is cached, hardcoded, or estimated.

---

## What it can do

| Area | What you get |
|---|---|
| Dashboard | One-page snapshot of revenue, expenses, net profit, receivables, payables, and pending invoices |
| Profit & Loss | Full P&L report for any date range |
| Trial Balance | Trial balance as of any date |
| Balance Sheet | Balance sheet as of any date |
| Receivables / Payables | Outstanding bills, with amounts and due dates |
| Overdue tracking | Receivables and payables past their due date |
| Pending invoices | Combined view of everything still open |
| Tally connection status | Quick check on whether the backend can actually reach Tally |
| Chatbot | Ask questions like *"show me overdue payables"* or *"what was our revenue in March"* and get a real answer |

---

## How the chatbot actually works

This is the part I'm most proud of, so it's worth explaining properly instead of just saying "AI-powered."

The chatbot **does not generate financial numbers itself.** Gemini is only used to figure out *which* Tally report the user is asking about it never touches the actual figures.

The flow looks like this:

```
User message
     │
     ▼
Gemini (tool selection only)
     │  picks one of 13 predefined, read-only tools
     ▼
Tool executor
     │  validates arguments, calls the matching Tally report
     ▼
Tally Prime (XML API)
     │  returns the real, current data
     ▼
Formatter
     │  turns the raw numbers into a plain-English answer
     ▼
Response sent back to the user
```

A few deliberate design choices here:

- **Gemini never sees or invents numbers.** Its only job is intent detection — mapping "who owes us the most" to the `get_highest_receivable` tool. The actual amount always comes straight from Tally.
- **13 fixed, read-only tools.** There's no open-ended code execution and no way for the model to call anything outside this list.
- **A write-request filter runs before the model is even asked.** If a message contains words like *delete, update, modify, create, post* etc., it's rejected immediately with a clear "this assistant is read-only" message. The model never gets a chance to attempt a write action.
- **Every date the model produces is re-validated** in DD-MM-YYYY format before it's used in a query, so a malformed or hallucinated date can't silently break a report.
- **Graceful degradation.** If Gemini is rate-limited, unauthenticated, or just unreachable, the backend catches it and returns a clean error instead of crashing the request.

In short: the LLM decides *what* to fetch, never *what the answer is.*

---

## Tech stack

**Backend**
- FastAPI (Python 3.13)
- httpx for async HTTP calls to Tally
- Pydantic / Pydantic Settings for config and schemas
- Google Gemini (`google-genai`) for chatbot tool selection
- Pytest for testing

**Frontend**
- React 19
- React Router for navigation
- Vite as the build tool

**Data source**
- Tally Prime, accessed over its native XML HTTP interface (default port `9000`)

---

## Project structure

```
tally-financial-intelligence/
├── backend/
│   ├── app/
│   │   ├── api/            # FastAPI routers (tally, dashboard, reports, chat)
│   │   ├── tally/           # Tally XML client, request builder, response parser
│   │   ├── financial/       # Business logic turns raw Tally data into clean reports
│   │   ├── chatbot/         # Gemini integration, tool registry, executor, policy, formatter
│   │   ├── core/             # Settings and logging config
│   │   └── main.py           # FastAPI app entrypoint
│   ├── tests/                 # Pytest suite covering parsing, calculations, and the chatbot
│   └── requirements.txt
│
└── frontend/
    ├── src/
    │   ├── pages/            # One page per report (Dashboard, P&L, Balance Sheet, etc.)
    │   ├── components/        # Shared layout and UI pieces (cards, tables, sidebar)
    │   ├── api/                # Fetch client for talking to the backend
    │   └── hooks/               # Data-fetching hook used across pages
    └── package.json
```

---

## Getting started

### Prerequisites

- Python 3.11+
- Node.js 18+
- Tally Prime running locally or reachable over the network, with its XML/HTTP gateway enabled
- A Gemini API key (only needed for the chatbot the dashboard works without it)

### 1. Backend setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # on Windows
# source .venv/bin/activate   # on macOS/Linux

pip install -r requirements.txt
```

Create a `.env` file inside `backend/` (this file is git-ignored on purpose never commit it):

```env
TALLY_HOST=localhost
TALLY_PORT=9000
TALLY_VERSION=prime

GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.6-flash
```

Run the API:

```bash
uvicorn app.main:app --reload
```

The backend comes up at `http://localhost:8000`. Interactive API docs are available at `http://localhost:8000/docs`.

### 2. Frontend setup

```bash
cd frontend
npm install
npm run dev
```

The dashboard runs at `http://localhost:5173` and talks to the backend automatically.

### 3. Run the tests

```bash
cd backend
pytest
```

---

## API overview

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/v1/tally/status` | Checks if Tally is reachable |
| GET | `/api/v1/tally/companies` | Lists companies open in Tally |
| GET | `/api/v1/dashboard/summary` | Full dashboard snapshot |
| GET | `/api/v1/reports/profit-loss` | Profit & Loss report |
| GET | `/api/v1/reports/trial-balance` | Trial Balance report |
| GET | `/api/v1/reports/balance-sheet` | Balance Sheet report |
| GET | `/api/v1/reports/receivables` | Outstanding receivables |
| GET | `/api/v1/reports/payables` | Outstanding payables |
| GET | `/api/v1/reports/pending-invoices` | Combined pending invoices |
| POST | `/api/v1/chat` | Ask the chatbot a financial question |

Full request/response schemas are visible in the auto-generated Swagger docs once the backend is running.

---

## A note on security

- `.env` holds live credentials (Tally host and the Gemini API key) and is already excluded via `.gitignore`  please keep it that way and never commit a real key.
- The chatbot is intentionally read-only end to end: the regex-based policy filter, the fixed tool list, and Tally's own API all reinforce the same boundary, so there's no single point that could let a write operation slip through.

---

