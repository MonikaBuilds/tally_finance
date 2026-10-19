# Tally Financial Intelligence (TFI)

A web dashboard, reporting suite and AI assistant for **Tally Prime**. TFI reads live data from Tally and presents it as dashboards, drill-down reports and a natural-language chat assistant, so teams can see financial and inventory positions in real-time without opening Tally desktop menus.

TFI is **strictly read-only**: it never writes or mutates anything in Tally.

---

## Table of Contents

1. [What TFI Does](#1-what-tfi-does)
2. [How It Works](#2-how-it-works)
3. [Tech Stack](#3-tech-stack)
4. [Software Required](#4-software-required)
5. [Getting Started (Step-by-Step)](#5-getting-started-step-by-step)
6. [Environment Variables](#6-environment-variables)
7. [Default Login (Super Admin)](#7-default-login-super-admin)
8. [Users, Roles and Permissions](#8-users-roles-and-permissions)
9. [API Reference](#9-api-reference)
10. [AI Assistant](#10-ai-assistant)
11. [Caching Architecture](#11-caching-architecture)
12. [Running the Tests](#12-running-the-tests)
13. [Project Structure](#13-project-structure)
14. [Troubleshooting](#14-troubleshooting)
15. [Security Notes](#15-security-notes)

---

## 1. What TFI Does

**Executive Financial Dashboard**
- Headline metrics: gross revenue, operating expenses, net profit, total receivables, total payables, cash & bank balances.
- Income vs. expense trends by month, overdue bill ageing buckets, top outstanding party rankings.

**Financial Statements & Ledgers**
- Profit & Loss, Balance Sheet, and Trial Balance with drill-down from groups to ledgers and individual vouchers.
- Ledger reports with 12-month summaries and complete voucher allocations.
- Receivables and Payables (bill-wise with ageing: 0–30, 31–60, 61–90, 90+ days) and pending sales/purchase invoices.

**Inventory & Godown Intelligence**
- Stock Summary by group, category, and godown location.
- Native Godown Monthly Summary (12-month matrix fetched directly from Tally's native `<ID>Item Monthly Summary</ID>` report, not synthetic approximations).
- Stock item vouchers with exact opening balance, inward/outward movements, running balances, and period totals.
- Stock valuation, movement analysis, and negative stock tracking.

**Report Exports**
- Download reports as **PDF** or formatted **Excel (.xlsx)** files with a single click.

**Deterministic AI Assistant (Chat)**
- Ask financial questions in plain English (e.g. *"What is our total receivable balance?"* or *"Compare this month's revenue with last month"*).
- Zero hallucination guarantee: Gemini identifies the user's intent and parameters, then fetches real ground-truth numbers directly from Tally XML. The AI never invents financial figures.

**Multi-Tenant Access Control**
- Complete company scoping: users only see transactions for Tally companies assigned to them.
- Granular RBAC (`superadmin`, `admin`, `user`) with bitmask permissions (`financial`, `inventory`, `banking`, `tax`).

**Resilient SWR Caching**
- Multi-tier Stale-While-Revalidate caching via Redis/Memurai delivers sub-millisecond report loads.
- Automatic fail-open circuit: if Redis is stopped or unreachable, the system queries Tally directly without failing.

---

## 2. How It Works

```
Browser (React 19 SPA)
      │  HTTPS/HTTP + HttpOnly JWT + CSRF Header Handshake
      ▼
FastAPI Backend Gateway  ◄──►  MySQL 8.0  (Users, roles, permissions, sessions)
      │
      ├───► Redis / Memurai   (SWR cache of Tally responses, optional)
      │
      ├───► Tally Prime       (XML/TDL over HTTP, port 9000, source of truth)
      │
      └───► Google Gemini     (Deterministic tool selection for AI chat)
```

1. The user logs in via the React SPA. The backend sets secure `access_token` and `refresh_token` cookies.
2. When a report is requested, the backend checks the Redis SWR cache. If fresh, it returns in `<1ms`.
3. On a cache miss, the backend generates a dynamic TDL XML request, sends it to Tally Prime's HTTP server (port 9000), parses the response with exact decimal precision, and caches the result.
4. For chat queries, a safety interceptor regex blocks any mutating requests. Gemini selects the appropriate read-only tool, queries live Tally data, and deterministic formatters return the response.

MySQL stores **only** system management data (users, organizations, roles, permissions, refresh tokens). All accounting data remains safely in Tally.

---

## 3. Tech Stack

| Layer | Technologies | Purpose |
| :--- | :--- | :--- |
| **Backend** | Python 3.13, FastAPI, Uvicorn, Pydantic | High-performance asynchronous REST API backend |
| **Frontend** | React 19, Vite, React Router 7, Lucide Icons | Modern, responsive client dashboard & reports |
| **Data Source** | Tally Prime (XML / TDL interface on port 9000) | Live system of record for all accounting and stock data |
| **Database** | MySQL 8.0 (`mysql-connector-python`) | Multi-tenant user authentication, RBAC, and sessions |
| **Caching** | Redis / Memurai (`redis-py`) | Stale-While-Revalidate (SWR) cache layer |
| **AI Engine** | Google Gemini 2.5 (`google-genai`), OpenRouter fallback | Natural-language intent detection and read-only tool invocation |
| **Security** | PBKDF2-HMAC-SHA256 (310k iterations), JWT, CSRF | Zero-trust authentication with HttpOnly cookies |
| **Export** | `openpyxl` (Excel), `reportlab` (PDF) | Report generation and spreadsheet download |
| **Testing** | Pytest, `pytest-asyncio`, Node test runner | Automated test coverage for parsers and endpoints |

---

## 4. Software Required

Install these prerequisites before starting:

| Software | Version | Purpose | Notes |
| :--- | :--- | :--- | :--- |
| **Python** | 3.13 | Backend API | **Crucial**: Check **"Add Python to PATH"** and select **"Install for all users"** during install. |
| **Node.js & npm** | 18+ or 20 LTS | Frontend build & dev server | Needed to install npm packages and run Vite. |
| **MySQL** | 8.0+ | Database | Install MySQL Server as a Windows Service. Remember your root password. |
| **Redis / Memurai** | 6.0+ | Fast Caching | On Windows, download the Windows-native installer from [memurai.com](https://www.memurai.com/). (Optional but recommended). |
| **Tally Prime** | Any release | Source of Truth | Running on the server with HTTP/XML server enabled on port 9000. |
| **VS Code & Git** | Latest | Code & Editing | Standard installations. |
| **Gemini API Key** | n/a | AI Chatbot | Free key from [Google AI Studio](https://aistudio.google.com/). *(Optional: chat assistant only)*. |

### Enable the XML Server in Tally Prime

1. Open **Tally Prime** on the server.
2. Press **`F1` (Help) > Settings > Connectivity > Client/Server configuration** and set:
   * **TallyPrime acts as**: `Both` (or `Server`)
   * **Port**: `9000`
3. Accept settings and restart Tally Prime.
4. **Open your target company in Tally Prime** (e.g. `ABC Pvt Ltd`). Tally only answers queries for companies that are currently loaded and open.

---

## 5. Getting Started (Step-by-Step)

Follow these steps to run the application on your Tally Server machine or local development computer. Commands are provided for **PowerShell**, **Command Prompt (CMD)**, and **Git Bash / macOS / Linux**.

### Step 1: Clone the Repository

Open your preferred terminal (**PowerShell**, **CMD**, or **Git Bash**):
```bash
git clone https://github.com/infintrix/tally-financial-intelligence.git tally_finance
cd tally_finance
```

---

### Step 2: Create the MySQL Database

Open MySQL Command Line Client (or run in terminal):
```sql
CREATE DATABASE tally_financial_intelligence CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

> [!NOTE]
> You **only** need to create this one empty database! You do **not** need to create tables or run manual SQL migration scripts. When the backend starts for the first time, it **automatically creates all tables** (`organizations`, `users`, `roles`, `permissions`, etc.) and bootstraps the default admin account.

*(Optional: If you prefer creating a dedicated user instead of using `root`):*
```sql
CREATE USER 'tfi_app'@'localhost' IDENTIFIED BY 'YourStrongPassword123!';
GRANT ALL PRIVILEGES ON tally_financial_intelligence.* TO 'tfi_app'@'localhost';
FLUSH PRIVILEGES;
```

---

### Step 3: Setup Redis (Memurai on Windows / Docker)

* **Windows (Recommended for Tally Server)**:
  1. Download and run the **Memurai** installer from [memurai.com](https://www.memurai.com/).
  2. Accept default port `6379`. It automatically starts as a Windows Service.
  3. Verify in your terminal (PowerShell, CMD, or Git Bash):
     ```bash
     memurai-cli ping
     # Expected response: PONG
     ```
* **Docker (For Linux/Mac or Local Dev)**:
  ```bash
  docker run -d --name tally-redis -p 6379:6379 redis:alpine
  ```
* **No Redis?** You can skip this step! Just set `REDIS_CACHE_ENABLED=false` in `backend/.env`. TFI is designed to fail open and will query Tally directly.

---

### Step 4: Set Up & Run the Backend

1. Navigate to the `backend` directory:
   ```bash
   cd backend
   ```

2. Create a Python virtual environment:
   ```bash
   python -m venv .venv
   ```

3. Activate the virtual environment:
   * **PowerShell**:
     ```powershell
     Set-ExecutionPolicy -Scope Process Bypass
     .venv\Scripts\Activate.ps1
     ```
   * **Command Prompt (CMD)**:
     ```cmd
     .venv\Scripts\activate.bat
     ```
   * **Git Bash / macOS / Linux**:
     ```bash
     source .venv/Scripts/activate    # Git Bash on Windows
     # or: source .venv/bin/activate  # macOS / Linux
     ```

4. Install backend dependencies:
   ```bash
   pip install -r requirements.txt
   ```

5. Create the `.env` configuration file from the template:
   * **PowerShell**:
     ```powershell
     Copy-Item .env.example .env
     ```
   * **Command Prompt (CMD)**:
     ```cmd
     copy .env.example .env
     ```
   * **Git Bash / macOS / Linux**:
     ```bash
     cp .env.example .env
     ```

6. Open `backend/.env` in Notepad or VS Code and set your values:
   * **`DB_PASSWORD`**: Your MySQL password.
   * **`DB_USER`**: Your MySQL user (`root` or `tfi_app`).
   * **`TALLY_HOST`**: `127.0.0.1` (or your Tally server IP).
   * **`TALLY_PORT`**: `9000`.
   * **`INITIAL_ADMIN_COMPANY`**: Set this to **exactly match your open Tally company name** (e.g. `ABC Pvt Ltd`).
   * **`CHAT_JWT_SECRET`**: Generate a secure 64-char key by running:
     * **PowerShell / CMD**:
       ```cmd
       python -c "import secrets; print(secrets.token_urlsafe(64))"
       ```
     * **Git Bash / macOS / Linux**:
       ```bash
       python3 -c "import secrets; print(secrets.token_urlsafe(64))"
       ```
     and paste the output into `CHAT_JWT_SECRET=`.
   * **`CORS_ALLOWED_ORIGINS`**: If accessing from other computers on your network, add your server IP:
     ```env
     CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://<SERVER-IP>:5173
     ```
   * **`GEMINI_API_KEY`**: Paste your Google Gemini API key here (if using AI chat).

7. Start the Backend API (works in PowerShell, CMD, and Git Bash):
   ```bash
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```
   > 💡 `--host 0.0.0.0` ensures the backend accepts requests both locally and from client PCs on your office network.

   * Test in browser: Open `http://localhost:8000/docs` to see the live Swagger API documentation!

---

### Step 5: Set Up & Run the Frontend

1. Open a **second terminal** and navigate to `frontend`:
   ```bash
   cd frontend
   ```

2. Create `frontend/.env` from the template:
   * **PowerShell**:
     ```powershell
     Copy-Item .env.example .env
     ```
   * **Command Prompt (CMD)**:
     ```cmd
     copy .env.example .env
     ```
   * **Git Bash / macOS / Linux**:
     ```bash
     cp .env.example .env
     ```

   * Ensure `frontend/.env` contains:
     ```env
     VITE_API_BASE_URL=http://localhost:8000/api/v1
     VITE_CSRF_COOKIE_NAME=csrf_token
     VITE_CSRF_HEADER_NAME=X-CSRF-Token
     ```
     *(Note: If users will access from other PCs on the network, replace `localhost` with your server IP, e.g. `VITE_API_BASE_URL=http://192.168.1.50:8000/api/v1`)*.

3. Install frontend dependencies:
   ```bash
   npm install
   ```

4. Start the frontend dev server:
   ```bash
   npm run dev
   ```
   *The frontend is now running on `http://localhost:5173` (or `http://<SERVER-IP>:5173`)*.

---

### Step 6: Log In and Explore

1. Open your browser and go to `http://localhost:5173` (or `http://<SERVER-IP>:5173`).
2. Log in with the default Super Admin credentials:
   * **Username**: `admin`
   * **Password**: `Admin@2026!`
3. Select your active Tally company from the top dropdown.
4. Your live dashboard, P&L, Balance Sheet, Godown Monthly Summary, and AI Chat are now running!

---

### Step 7 (Optional): Production Build for Frontend

To compile the frontend into an optimized static distribution:
```bash
cd frontend
npm run build
```
The output will be in `frontend/dist`. You can serve it using any web server (e.g. `npx serve dist -s -l 5173` or Microsoft IIS).

---

## 6. Environment Variables

### 6.1 Backend (`backend/.env`)

A reference template is available in `backend/.env.example`.

**Tally Configuration**

| Variable | Example | Description |
| :--- | :--- | :--- |
| `TALLY_HOST` | `127.0.0.1` | IP address or hostname of machine running Tally Prime |
| `TALLY_PORT` | `9000` | Port configured in Tally Prime Client/Server settings |
| `TALLY_VERSION` | `prime` | Tally edition (`prime` or `erp9`) |
| `TALLY_UNAVAILABLE_COOLDOWN_SECONDS` | `30` | Seconds to wait before re-probing after Tally is unavailable |

**Database (MySQL)**

| Variable | Example | Description |
| :--- | :--- | :--- |
| `DB_HOST` | `localhost` | MySQL host address |
| `DB_PORT` | `3306` | MySQL port |
| `DB_NAME` | `tally_financial_intelligence` | MySQL database name |
| `DB_USER` | `root` or `tfi_app` | MySQL username |
| `DB_PASSWORD` | `<your-password>` | MySQL password |

**Authentication & Security**

| Variable | Default | Description |
| :--- | :--- | :--- |
| `CHAT_AUTH_ENABLED` | `true` | Enforces authentication check |
| `CHAT_JWT_SECRET` | none (**required**) | 64+ char cryptographic secret for signing JWT access tokens |
| `CHAT_JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `CHAT_JWT_EXPIRE_MINUTES` | `60` | Access token lifespan |
| `AUTH_COOKIE_SECURE` | `false` | Set `true` when serving over HTTPS |
| `AUTH_COOKIE_SAMESITE` | `lax` | Browser cookie policy (`lax`, `strict`, `none`) |
| `AUTH_CSRF_COOKIE_NAME` | `csrf_token` | CSRF cookie name (must match frontend) |
| `AUTH_CSRF_HEADER_NAME` | `X-CSRF-Token` | CSRF header name (must match frontend) |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173` | Comma-separated list of origins allowed to call the API |

**Initial Super Admin (Created on First Start)**

| Variable | Default | Description |
| :--- | :--- | :--- |
| `INITIAL_ADMIN_USERNAME` | `admin` | Initial superadmin username |
| `INITIAL_ADMIN_PASSWORD` | `Admin@2026!` | Initial superadmin password |
| `INITIAL_ADMIN_COMPANY` | `ABC Pvt Ltd` | **Must exactly match** your active open Tally company name |

**AI Assistant (Optional)**

| Variable | Default | Description |
| :--- | :--- | :--- |
| `GEMINI_API_KEY` | none | Google Gemini API key from AI Studio |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model name |
| `OPENROUTER_API_KEY` | none | Optional fallback API provider key |

**Redis Cache (Optional)**

| Variable | Default | Description |
| :--- | :--- | :--- |
| `REDIS_CACHE_ENABLED` | `true` | Enables/disables caching (`false` fails open to Tally) |
| `REDIS_URL` | `redis://127.0.0.1:6379/0` | Redis / Memurai connection URL |
| `REDIS_CACHE_DEFAULT_FRESH_TTL` | `300` | Fresh cache window in seconds (5 minutes) |
| `REDIS_CACHE_STALE_RETENTION_TTL` | `86400` | Stale cache retention in seconds (24 hours) |

### 6.2 Frontend (`frontend/.env`)

| Variable | Example | Description |
| :--- | :--- | :--- |
| `VITE_API_BASE_URL` | `http://localhost:8000/api/v1` | Base URL of backend API including `/api/v1` |
| `VITE_CSRF_COOKIE_NAME` | `csrf_token` | Must equal backend `AUTH_CSRF_COOKIE_NAME` |
| `VITE_CSRF_HEADER_NAME` | `X-CSRF-Token` | Must equal backend `AUTH_CSRF_HEADER_NAME` |

---

## 7. Default Login (Super Admin)

When the backend starts against a clean database for the first time, it automatically creates the Super Admin account:

* **Username**: `admin`
* **Password**: `Admin@2026!`
* **Roles**: `superadmin` and `admin` with all permissions (`financial`, `inventory`, `banking`, `tax`).

> [!IMPORTANT]
> The initial admin is created **only once when the users table is completely empty**. Once any user exists, the bootstrapper permanently skips. Always change the default admin password upon first login!

---

## 8. Users, Roles and Permissions

**Roles Hierarchy**
* `superadmin`: Full platform control, including creating and managing other admins.
* `admin`: Manages users and permissions within their organization.
* `user`: Accesses reports, dashboard, and AI chat according to assigned permissions.

**Granular Permissions**
* `financial`: Profit & Loss, Balance Sheet, Trial Balance, Receivables, Payables, Ledgers.
* `inventory`: Stock Summary, Godowns, Monthly Item Summary, Stock Vouchers.
* `banking`: Cash and bank ledger positions and accounts.
* `tax`: Tax ledgers, TDS, and GST summaries.

**Company Access**
Users can only query Tally companies assigned to them. Any attempt to query unassigned companies is rejected with HTTP 403.

---

## 9. API Reference

Interactive Swagger documentation is available live at `http://localhost:8000/docs`.

### Key Endpoints
* **Authentication**: `POST /api/v1/auth/login`, `GET /api/v1/auth/me`, `POST /api/v1/auth/logout`, `POST /api/v1/auth/change-password`
* **Administration**: `GET /api/v1/admin/users`, `POST /api/v1/admin/users`, `DELETE /api/v1/admin/users/{id}`, `PUT /api/v1/admin/users/{id}/companies`
* **Tally Diagnostics**: `GET /api/v1/tally/status`, `GET /api/v1/tally/companies`
* **Dashboard**: `GET /api/v1/dashboard/summary`, `GET /api/v1/dashboard/monthly`
* **AI Chat**: `POST /api/v1/chat`
* **Reports**:
  * P&L: `GET /api/v1/reports/profit-loss`, `GET /api/v1/reports/profit-loss/export/{file_format}`
  * Balance Sheet: `GET /api/v1/reports/balance-sheet`, `GET /api/v1/reports/balance-sheet/export/{file_format}`
  * Trial Balance: `GET /api/v1/reports/trial-balance`
  * Ledgers & Vouchers: `GET /api/v1/reports/ledgers`, `GET /api/v1/reports/ledger`, `GET /api/v1/reports/voucher`
  * Receivables & Payables: `GET /api/v1/reports/receivables`, `GET /api/v1/reports/payables`
  * Inventory: `GET /api/v1/reports/stock-summary`, `GET /api/v1/reports/godown-summary`, `GET /api/v1/reports/stock-item-monthly`, `GET /api/v1/reports/stock-item-vouchers`

---

## 10. AI Assistant

The deterministic AI assistant processes questions in 4 stages:
1. **Safety Interceptor**: Blocks any request attempting write, update, or delete commands.
2. **Deterministic Rules**: Matches common questions locally for instant zero-cost responses.
3. **Gemini Tool Selection**: Maps complex natural-language queries to one of over 70 read-only financial tools.
4. **Live ERP Ground Truth**: Fetches audited accounting data directly from Tally Prime XML and passes it through deterministic formatters. The LLM never computes or invents numbers.

---

## 11. Caching Architecture

* **Fresh Response (< 300s)**: Cached JSON is delivered instantaneously in `< 1ms`.
* **Stale Response (< 24 hours)**: If Tally Prime is busy or briefly closed, TFI serves cached data seamlessly marked with `is_stale: true` while triggering an asynchronous background revalidation.
* **Fail-Open Circuit**: If Redis/Memurai is stopped, requests bypass the cache and query Tally Prime directly without crashing or throwing 500 errors.
* **Bypass Cache**: Add `force_refresh=true` to any report API call to bypass the cache.

---

## 12. Running the Tests

Backend automated test suite (run from `backend/` with venv active):
```bash
pytest
```
*Run inventory and native Tally parser tests:*
```bash
pytest tests/test_godown_monthly_direct_tally.py tests/test_parser.py tests/test_xml_builder.py
```

Frontend unit tests (run from `frontend/`):
```bash
npm test
npm run lint
```

---

## 13. Project Structure

```
tally_finance/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI lifecycle, startup hooks, table initializations
│   │   ├── api/               # REST API endpoints (auth, admin, reports, dashboard, chat)
│   │   ├── tally/             # Native Tally XML client, TDL request builders, XML parsers
│   │   ├── chatbot/           # Gemini intent router, tool registry, safety policy
│   │   ├── security/          # PBKDF2 hashing, JWT/cookie handling, RBAC, user store
│   │   ├── cache/             # Redis client, SWR manager, background cache refresher
│   │   ├── export/            # PDF and Excel report generators
│   │   ├── financial/         # Business intelligence & calculations
│   │   └── core/              # Configuration, logging, exception handlers
│   ├── tests/                 # Automated test suite
│   ├── requirements.txt       # Python dependencies
│   └── .env.example           # Reference backend environment variables
└── frontend/
    ├── src/
    │   ├── pages/             # Report views (Dashboard, P&L, Godown, Vouchers, Chat)
    │   ├── components/        # Reusable UI components (Tables, KPI cards, Navbar)
    │   ├── api/client.js      # Fetch client with cookie/CSRF interceptors
    │   ├── hooks/             # Data fetching and company year hooks
    │   └── App.jsx            # Routing and authentication guards
    ├── package.json           # Frontend dependencies (React 19, Lucide, Vite)
    └── .env.example           # Reference frontend environment variables
```

---

## 14. Troubleshooting

| Problem | Probable Cause | Verified Resolution |
| :--- | :--- | :--- |
| **Backend exits: `'Required environment variable ... is not configured'`** | Missing mandatory key in `backend/.env`. | Ensure `CHAT_JWT_SECRET`, `DB_NAME`, and `DB_PASSWORD` are filled in `backend/.env` without spaces around `=`. |
| **MySQL `'Access denied'` or `'Unknown database'`** | Database not created or wrong credentials. | Run `CREATE DATABASE tally_financial_intelligence;` in MySQL, and confirm `DB_USER` & `DB_PASSWORD` in `.env` match your MySQL credentials. |
| **Dashboard empty or `'Tally unavailable'`** | Tally Prime is closed, company is not open, or XML server is off. | 1. Open Tally Prime on the server.<br>2. Load your company (name must match `INITIAL_ADMIN_COMPANY` exactly).<br>3. Confirm `F1 > Settings > Connectivity` is set to `Both` on Port `9000`. |
| **Frontend displays: `VITE_API_BASE_URL is not configured`** | Missing `frontend/.env`. | Copy `frontend/.env.example` to `frontend/.env` and restart Vite (`npm run dev`). |
| **Login succeeds, but subsequent requests fail with 401/403** | CORS mismatch or cookie secure issue. | 1. Ensure `CORS_ALLOWED_ORIGINS` in `backend/.env` matches your browser URL.<br>2. For plain HTTP on internal LANs, verify `AUTH_COOKIE_SECURE=false`. |
| **Script execution error in PowerShell (`Activate.ps1`)** | Windows execution policy restriction. | Run `Set-ExecutionPolicy -Scope Process Bypass` in PowerShell, then activate `.venv\Scripts\Activate.ps1` again. |
| **Redis connection warning in logs** | Redis/Memurai is not running. | Memurai is optional. TFI fails open automatically. To enable caching, start the Memurai service (`Start-Service Memurai`). |
| **AI Assistant / Chatbot fails** | Missing or invalid Gemini API key. | Ensure `GEMINI_API_KEY` is set in `backend/.env` and the server can access outbound internet. |

---

## 15. Security Notes

* **Secret Hygiene**: Keep `.env` files private. Generate unique random strings for `CHAT_JWT_SECRET`.
* **Change Default Passwords**: Immediately rotate the `admin` / `Admin@2026!` password upon initial login.
* **Port Isolation**: Keep ports `9000` (Tally Prime), `3306` (MySQL), and `6379` (Redis) bound strictly to `127.0.0.1`. Never expose them to the public internet.
* **Database Backups**: Schedule regular backups of MySQL (`mysqldump`). All users, permissions, and organizations reside in MySQL.
