# Lyftr AI - LLM Chatbot with Key Failover and Response Caching

Lyftr AI is a full-stack AI chatbot built using React, FastAPI, SQLite, LiteLLM and Google Gemini.

The application supports multi-turn conversations, automatic API-key failover, LiteLLM response caching, per-request token tracking, latency tracking, failure simulation and Docker-based deployment.

---

## 1. Live URLs

- Frontend: https://lyftr-ai-frontend-4slf.onrender.com
- Backend: https://lyftr-ai-backend-xxxq.onrender.com
- Backend Health: https://lyftr-ai-backend-xxxq.onrender.com/health
- Swagger API Docs: https://lyftr-ai-backend-xxxq.onrender.com/docs
- GitHub Repository: https://github.com/Jashandeep-K/lyftr-ai-assignment

---

## 2. Run locally: with Docker and without

### Environment Setup

Create a file named `.env` inside the `backend` directory.

```env
LLM_API_KEYS=your_first_api_key,your_second_api_key
LLM_MODEL=gemini/gemini-3.5-flash-lite
DATABASE_URL=sqlite:///./app.db
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000
ENABLE_FAILURE_SIMULATION=true
```

Real API keys must never be committed to GitHub.

### Run with Docker

Docker Desktop and Docker Compose are required.

From the project root run:

```bash
make up
```

This starts:

- Frontend: http://localhost:3000
- Backend: http://localhost:8000
- Swagger Docs: http://localhost:8000/docs

The SQLite database is stored at `/data/app.db` using a named Docker volume so conversation history survives container restarts.

To stop the application:

```bash
make down
```

Alternatively:

```bash
docker compose up --build
```

and:

```bash
docker compose down
```

### Run without Docker

#### Backend

```bash
cd backend
python -m venv venv
```

Activate the virtual environment.

On Windows:

```powershell
.\venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Start FastAPI:

```bash
uvicorn main:app --reload --port 8000
```

Backend will run at:

```text
http://localhost:8000
```

#### Frontend

Open another terminal:

```bash
cd frontend
npm install
npm run dev
```

The Vite development frontend will run at:

```text
http://localhost:5173
```

---

## 3. Design decisions: key fallback, caching, SQLite session storage

### Multi-turn Conversation

Every browser page load creates a new session ID.

The frontend sends only the new user message and the session ID to the backend.

The backend retrieves previous messages for that session from SQLite and constructs the complete conversation before sending it to the LLM.

This allows the chatbot to remember previous messages while keeping different sessions separate.

### API Key Pool and Automatic Fallback

Multiple Gemini API keys are supplied using:

```text
LLM_API_KEYS
```

The keys are internally identified as:

```text
key_1
key_2
...
```

If one provider request fails, the backend automatically attempts the next configured key.

The API response reports which key successfully handled the request and how many fallback attempts occurred.

For example, if `key_1` fails and `key_2` succeeds:

```json
{
  "key_id": "key_2",
  "fallback_attempts": 1
}
```

If every configured key fails, the API returns:

```json
{
  "detail": "all providers unavailable"
}
```

with HTTP status `503`.

Failed requests are not added to conversation history.

### Failure Simulation

The backend supports the required `X-Simulate-Failure` request header when:

```text
ENABLE_FAILURE_SIMULATION=true
```

Examples:

```text
X-Simulate-Failure: key_1=429
X-Simulate-Failure: key_1=500
X-Simulate-Failure: key_1=429,key_2=500
X-Simulate-Failure: *=429
```

This allows failover behavior to be demonstrated without intentionally exhausting real API keys.

### LiteLLM Response Caching

LiteLLM's built-in local cache is enabled.

The cache is based on the model and complete message list sent to the LLM.

A newly generated response reports:

```text
LIVE_INFERENCE
```

A cached response reports:

```text
LLM_CACHE
```

For a cache hit:

- The reply is identical to the original response.
- Input and output token usage is preserved.
- `key_id` is `null`.
- `fallback_attempts` is `0`.
- Cache latency is lower than live inference.

### SQLite Session Storage

Conversation history is stored in SQLite.

Each stored message contains:

- Session ID
- Role
- Content
- Assistant metadata
- Creation timestamp

The schema is created automatically when the backend starts.

When Docker is used, the database is stored at:

```text
/data/app.db
```

using a named Docker volume.

---

## 4. Verification: how to see failover, cache hits and per-message token usage

### Health Check

Request:

```http
GET /health
```

Expected response:

```json
{
  "status": "ok",
  "keys_configured": 2,
  "cache_enabled": true
}
```

### Verify Multi-turn Memory

Send:

```text
My name is Alex.
```

Then, using the same session:

```text
What is my name?
```

The assistant should remember that the name is Alex.

### Verify Cache

Send the same first message using two different new session IDs.

Example:

```text
What is the capital of Japan?
```

The first request should report:

```text
LIVE_INFERENCE
```

The same first message in another new session should report:

```text
LLM_CACHE
```

The cached response should contain the same reply and token counts with lower latency.

### Verify Key Failover

Open Swagger at:

```text
/backend-url/docs
```

Send a `POST /chat` request with:

```text
X-Simulate-Failure: key_1=429
```

The response should succeed with:

```json
{
  "key_id": "key_2",
  "fallback_attempts": 1
}
```

### Verify All Keys Failing

Use:

```text
X-Simulate-Failure: *=429
```

The API should return HTTP `503`:

```json
{
  "detail": "all providers unavailable"
}
```

The failed request is not added to session history.

### Per-request Token Usage

Every assistant response displays:

- Resolution source
- Model
- Latency in milliseconds
- Input tokens
- Output tokens

Token counts represent the individual request rather than a running conversation total.

### Automated Backend Tests

Run:

```bash
cd backend
pytest -v
```

The automated test suite covers:

- Health endpoint
- Request validation
- Empty message validation
- Message length validation
- Successful chat request
- Session history
- Unknown session handling
- 429 key fallback
- 500 key fallback
- All-key failure
- Failed requests not being stored

---

## 5. Setup Used: editor and AI tools

The project was developed using:

- Visual Studio Code
- Python
- FastAPI
- SQLAlchemy
- SQLite
- LiteLLM
- Google Gemini
- React
- Vite
- Docker Desktop
- Docker Compose
- WSL 2
- Git
- GitHub
- Render
- ChatGPT for development assistance, debugging and documentation

---

## 6. Bonus features (if any): what you added beyond the requirements and why

The project includes several additional usability features:

- Responsive dark-mode chatbot interface
- Configurable system prompt
- Loading animation while waiting for an AI response
- Visible session identifier
- Automatic scrolling to the latest message
- Readable frontend error messages
- Backend connection indicator
- Automated backend test suite
- Responsive interface for smaller screens

---

## API Endpoints

### GET /health

Checks backend status, configured key count and caching status.

### POST /chat

Sends a new message to the chatbot.

Example request:

```json
{
  "session_id": "s-7f3a",
  "message": "What is the capital of France?"
}
```

### GET /sessions/{session_id}/messages

Returns stored conversation history for the specified session in oldest-first order.

---

## Repository Structure

```text
lyftr-ai-assignment/
│
├── backend/
│   ├── tests/
│   │   └── test_api.py
│   ├── Dockerfile
│   ├── database.py
│   ├── main.py
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   ├── Dockerfile
│   ├── package.json
│   └── vite.config.js
│
├── docker-compose.yml
├── Makefile
├── .env.example
├── .gitignore
└── README.md
```

---

## Security

API keys are provided through environment variables and are never hard-coded into the source code.

The real `.env` file is excluded using `.gitignore`.

Only placeholder values are provided in `.env.example`.