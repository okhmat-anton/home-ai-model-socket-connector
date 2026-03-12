# Home AI Model Socket Connector

A bidirectional bridge between a local AI model and the outside world.

## Two Operating Modes

| Mode | Direction | Transport | Port |
|------|-----------|-----------|------|
| **Incoming** | user → server → model | REST API + Socket.IO | 10666 |
| **Outgoing** | model → server → internet | HTTPS proxy (HTTP CONNECT) | 10667 |

### Incoming Mode

A user sends a REST request → the server forwards it to the model via Socket.IO → the model responds → the server returns the response to the user.

### Outgoing Mode

The model configures a standard HTTPS proxy (`HTTPS_PROXY`) and accesses the internet through the server's IP. Authentication is username/password (Basic Auth via `Proxy-Authorization`).

---

## Quick Start (AWS Lightsail)

```bash
# 1. Clone the repository
sudo yum install -y git   # AL2
# sudo dnf install -y git  # AL2023
git clone <repo-url> ~/home-ai-model-socket-connector
cd ~/home-ai-model-socket-connector

# 2. Open ports in Lightsail Networking (IPv4 Firewall):
#    TCP 10666 — REST API + Socket.IO
#    TCP 10667 — HTTPS proxy
#    (TCP 80 + 443 if using SSL with make add-domain)

# 3. Install dependencies + set up systemd
make install

# 4. Generate keys
make gen-keys

# 5. Edit .env if needed
nano .env

# 6. Start the service
make run

# 7. (Optional) Add SSL for your domain
make add-domain domain=your-domain.com
```

## Makefile Commands

| Command | Description |
|---------|-------------|
| `make install` | Install Python 3.11, venv, dependencies, and systemd service (AL2 + AL2023) |
| `make run` | Start the service |
| `make stop` | Stop the service |
| `make restart` | Restart the service |
| `make update` | `git pull` + update dependencies + auto-rollback on test failures |
| `make test` | Run tests |
| `make logs` | View logs (`journalctl -f`) |
| `make status` | Show systemd service status |
| `make gen-keys` | Generate random keys → `.env` |
| `make add-domain domain=X` | Install Caddy + auto-SSL for domain X (Let's Encrypt) |
| `make remove-domain` | Remove Caddy and SSL config |
| `make uninstall` | Remove the systemd service |

---

## Configuration (.env)

Copy from `.env.example`:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `10666` | REST API + Socket.IO port |
| `MODEL_API_KEY` | — | API key for model connection (Socket.IO) |
| `USER_API_KEY` | — | API key for users (REST) |
| `SECRET_KEY` | — | Secret for signing JWT tokens |
| `REQUEST_TIMEOUT` | `1800` | Model response timeout (seconds) |
| `MAX_CONCURRENT_REQUESTS` | `10` | Max concurrent requests to model |
| `PROXY_PORT` | `10667` | HTTPS proxy port |
| `PROXY_USER` | `proxy` | Proxy username |
| `PROXY_PASSWORD` | — | Proxy password |
| `PROXY_ALLOWED_DOMAINS` | `*` | Comma-separated domain list or `*` for all |
| `PROXY_MAX_CONNECTIONS` | `50` | Max concurrent proxy connections |
| `LOG_LEVEL` | `INFO` | Log level |

---

## REST API

### `GET /health`
Server status (no authorization required).

### `GET /instruction`
Plain-text instruction for an AI agent with live values.

### `POST /ask`
Send a prompt to the model.

**Header:** `Authorization: Bearer <USER_API_KEY>`

```json
{
  "prompt": "Hello!",
  "model": "llama3",
  "stream": false,
  "request_id": "my-correlation-id",
  "parameters": {
    "temperature": 0.7,
    "max_tokens": 2048
  }
}
```

Fields `model`, `stream`, `parameters`, `request_id` are optional.
If `request_id` is omitted the server generates a UUID. Use it to correlate responses when sending multiple requests concurrently.

**Response:**
```json
{
  "request_id": "my-correlation-id",
  "response": "Hello! How can I help you?",
  "model": "llama3",
  "usage": {
    "prompt_tokens": 5,
    "completion_tokens": 12,
    "total_tokens": 17
  },
  "elapsed_seconds": 1.3
}
```

With `"stream": true` the response is delivered as Server-Sent Events (SSE).
Every SSE chunk includes `request_id` for correlation.

### Concurrent Async Requests

You can fire multiple requests simultaneously. Each response is matched by `request_id`:

```python
import asyncio, httpx

async def ask(client, prompt, rid):
    resp = await client.post("/ask", json={
        "prompt": prompt,
        "request_id": rid,
    })
    return resp.json()  # {"request_id": rid, "response": "...", ...}

async def main():
    headers = {"Authorization": "Bearer <USER_API_KEY>"}
    async with httpx.AsyncClient(
        base_url="https://server:10666", headers=headers
    ) as c:
        tasks = [ask(c, f"Question {i}", f"q-{i}") for i in range(10)]
        results = await asyncio.gather(*tasks)
        for r in results:
            print(r["request_id"], r["response"][:50])

asyncio.run(main())
```

### `GET /models`
List connected models.

**Header:** `Authorization: Bearer <USER_API_KEY>`

### `POST /auth/token`
Obtain a JWT token (optional).

### `GET /errors`
Query the error log. Returns recent errors, filterable by `request_id` or event type.

**Header:** `Authorization: Bearer <USER_API_KEY>`

**Query parameters:**

| Parameter | Description |
|-----------|-------------|
| `request_id` | Filter errors by specific request ID |
| `event` | Filter by event type (e.g. `ask_timeout`, `auth_invalid`, `inference_error`) |
| `limit` | Max entries to return (default: 50, max: 500) |

**Examples:**
```bash
# Get all recent errors
curl -H "Authorization: Bearer <KEY>" http://server:10666/errors

# Look up errors for a specific request
curl -H "Authorization: Bearer <KEY>" "http://server:10666/errors?request_id=<uuid>"

# Get all timeout errors
curl -H "Authorization: Bearer <KEY>" "http://server:10666/errors?event=ask_timeout"
```

**Response:**
```json
{
  "total": 1,
  "errors": [
    {
      "request_id": "a1b2c3d4-...",
      "timestamp": 1741782000.0,
      "iso_time": "2026-03-12T10:00:00Z",
      "event": "ask_timeout",
      "detail": "Model response timed out",
      "model": "llama3",
      "timeout": 1800
    }
  ]
}
```

**Error event types:**

| Event | Description |
|-------|-------------|
| `model_not_found` | Requested model is not connected |
| `model_disconnected` | Model disconnected during a request |
| `ask_timeout` | Model didn't respond within timeout |
| `inference_error` | Model returned an error |
| `model_inference_error` | Model reported an error via Socket.IO |
| `stream_timeout` | Streaming response timed out |
| `stream_error` | Error during streaming response |
| `rate_limited` | Too many concurrent requests |
| `auth_missing` | Request missing authorization header |
| `auth_invalid` | Invalid or expired token |

---

## Socket.IO (Model Side)

The model connects to the `/model` namespace on port 10666.

**Connection:**
```python
import socketio

sio = socketio.AsyncClient()
await sio.connect(
    "http://<server-ip>:10666",
    namespaces=["/model"],
    auth={"api_key": "<MODEL_API_KEY>", "model_name": "my-model"},
)
```

**Events:**
- `inference_request` — server sends an inference request to the model
- `inference_response` — model returns the full result
- `inference_chunk` — model sends a streaming chunk
- `inference_error` — model reports an error
- `ping` / `pong` — keepalive

---

## HTTPS Proxy (Model Side)

Port `10667`. Authentication: `Proxy-Authorization: Basic <base64(user:pass)>`.

```python
import httpx

client = httpx.Client(
    proxy="http://proxy:password@server-ip:10667"
)
resp = client.get("https://api.example.com/data")
```

Or via environment variables:

```bash
export HTTPS_PROXY=http://proxy:password@server-ip:10667
export HTTP_PROXY=http://proxy:password@server-ip:10667
```

---

## Project Structure

```
├── .env.example
├── .gitignore
├── Makefile
├── README.md
├── requirements.txt
├── technical_requirements.txt
├── systemd/
│   └── home-ai-connector.service
├── src/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── schemas.py
│   ├── auth.py
│   ├── error_store.py
│   ├── model_registry.py
│   ├── socketio_handlers.py
│   ├── proxy_server.py
│   ├── instruction.txt
│   └── routes/
│       ├── __init__.py
│       ├── instruction.py
│       ├── health.py
│       ├── ask.py
│       ├── models.py
│       ├── auth.py
│       └── errors.py
└── tests/
    ├── conftest.py
    ├── test_auth.py
    ├── test_ask.py
    ├── test_concurrency.py
    ├── test_config.py
    ├── test_health.py
    ├── test_instruction.py
    ├── test_models.py
    ├── test_proxy.py
    └── test_socketio.py
```

---

## Tests

```bash
make test
# or directly
venv/bin/pytest tests/ -v --tb=short
```

---

## Networking (Lightsail)

Open the following ports in **Lightsail Console → Instance → Networking → IPv4 Firewall → Add rule**:

| Port | Protocol | Purpose |
|------|----------|---------|
| **10666** | TCP | REST API + Socket.IO |
| **10667** | TCP | HTTPS proxy |
| **80** | TCP | HTTP (only if using `make add-domain` for SSL) |
| **443** | TCP | HTTPS (only if using `make add-domain` for SSL) |

> **Without these rules the ports are blocked by default and connections will time out.**

---

## License

MIT
