# Home AI Model Socket Connector

Двунаправленный мост между локальной ИИ-моделью и внешним миром.

## Два режима работы

| Режим | Направление | Транспорт | Порт |
|-------|------------|-----------|------|
| **Входящий** | user → server → model | REST API + Socket.IO | 10666 |
| **Исходящий** | model → server → internet | HTTPS-прокси (HTTP CONNECT) | 10667 |

### Входящий режим

Пользователь отправляет REST-запрос → сервер пересылает задание модели по Socket.IO → модель отвечает → сервер возвращает ответ пользователю.

### Исходящий режим

Модель настраивает стандартный HTTPS-прокси (`HTTPS_PROXY`) и выходит в интернет через IP сервера. Аутентификация — логин/пароль (Basic Auth на `Proxy-Authorization`).

---

## Быстрый старт (Amazon Linux 2 / Lightsail)

```bash
# 1. Клонировать репозиторий
git clone <repo-url> ~/home-ai-model-socket-connector
cd ~/home-ai-model-socket-connector

# 2. Установить зависимости + настроить systemd
make install

# 3. Сгенерировать ключи
make gen-keys

# 4. Отредактировать .env если нужны правки
nano .env

# 5. Запустить
make run
```

## Makefile-команды

| Команда | Описание |
|---------|----------|
| `make install` | Установка Python 3.11, venv, зависимостей, systemd-сервиса |
| `make run` | Запуск сервиса |
| `make stop` | Остановка сервиса |
| `make restart` | Перезапуск |
| `make update` | `git pull` + обновление зависимостей + авто-откат при ошибках тестов |
| `make test` | Запуск тестов |
| `make logs` | Просмотр логов (`journalctl -f`) |
| `make status` | Статус systemd-сервиса |
| `make gen-keys` | Генерация случайных ключей → `.env` |
| `make uninstall` | Удаление systemd-сервиса |

---

## Конфигурация (.env)

Скопировать из `.env.example`:

```bash
cp .env.example .env
```

| Переменная | По умолчанию | Описание |
|-----------|-------------|----------|
| `HOST` | `0.0.0.0` | Адрес привязки сервера |
| `PORT` | `10666` | Порт REST API + Socket.IO |
| `BASE_MODEL` | `llama3` | Модель по умолчанию |
| `MODEL_API_KEY` | — | API-ключ для подключения модели (Socket.IO) |
| `USER_API_KEY` | — | API-ключ для пользователей (REST) |
| `SECRET_KEY` | — | Секрет для подписи JWT-токенов |
| `REQUEST_TIMEOUT` | `1800` | Таймаут ответа модели (сек) |
| `MAX_CONCURRENT_REQUESTS` | `10` | Макс. параллельных запросов к модели |
| `PROXY_PORT` | `10667` | Порт HTTPS-прокси |
| `PROXY_USER` | `proxy` | Логин прокси |
| `PROXY_PASSWORD` | — | Пароль прокси |
| `PROXY_ALLOWED_DOMAINS` | `*` | Список доменов через `,` или `*` |
| `PROXY_MAX_CONNECTIONS` | `50` | Макс. одновременных прокси-соединений |
| `LOG_LEVEL` | `INFO` | Уровень логирования |

---

## REST API

### `GET /health`
Статус сервера (без авторизации).

### `GET /instruction`
Текстовая инструкция для ИИ-агента с актуальными значениями.

### `POST /ask`
Отправка запроса к модели.

**Заголовок:** `Authorization: Bearer <USER_API_KEY>`

```json
{
  "prompt": "Привет!",
  "model": "llama3",
  "stream": false,
  "parameters": {
    "temperature": 0.7,
    "max_tokens": 2048
  }
}
```

Поля `model`, `stream`, `parameters` — опциональные.

**Ответ:**
```json
{
  "response": "Привет! Чем могу помочь?",
  "model": "llama3",
  "usage": {
    "prompt_tokens": 5,
    "completion_tokens": 12,
    "total_tokens": 17
  },
  "elapsed_seconds": 1.3
}
```

С `"stream": true` — ответ приходит как Server-Sent Events (SSE).

### `GET /models`
Список подключённых моделей.

**Заголовок:** `Authorization: Bearer <USER_API_KEY>`

### `POST /auth/token`
Получение JWT-токена (опционально).

---

## Socket.IO (для модели)

Модель подключается к namespace `/model` на порту 10666.

**Подключение:**
```python
import socketio

sio = socketio.AsyncClient()
await sio.connect(
    "http://<server-ip>:10666",
    namespaces=["/model"],
    auth={"api_key": "<MODEL_API_KEY>", "model_name": "my-model"},
)
```

**События:**
- `inference_request` → сервер отправляет запрос модели
- `inference_response` → модель возвращает результат
- `inference_chunk` → модель отправляет часть потокового ответа
- `inference_error` → модель сообщает об ошибке
- `ping` / `pong` → keepalive

---

## HTTPS-прокси (для модели)

Порт `10667`. Аутентификация: `Proxy-Authorization: Basic <base64(user:pass)>`.

```python
import httpx

client = httpx.Client(
    proxy="http://proxy:password@server-ip:10667"
)
resp = client.get("https://api.example.com/data")
```

Или через переменные окружения:

```bash
export HTTPS_PROXY=http://proxy:password@server-ip:10667
export HTTP_PROXY=http://proxy:password@server-ip:10667
```

---

## Структура проекта

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
│       └── auth.py
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

## Тесты

```bash
make test
# или напрямую
venv/bin/pytest tests/ -v --tb=short
```

---

## Сеть (Lightsail)

В Lightsail Networking откройте:
- **TCP 10666** — REST API + Socket.IO
- **TCP 10667** — HTTPS-прокси

---

## Лицензия

MIT
