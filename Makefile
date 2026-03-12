SHELL := /bin/bash
.PHONY: install run stop restart update test logs status gen-keys uninstall

PYTHON := python3.11
VENV := venv
PIP := $(VENV)/bin/pip
PYTEST := $(VENV)/bin/pytest
SERVICE := home-ai-connector

# Standalone Python 3.11 binary (no compilation needed)
PYTHON_STANDALONE_URL := https://github.com/indygreg/python-build-standalone/releases/download/20240726/cpython-3.11.9+20240726-x86_64-unknown-linux-gnu-install_only.tar.gz

install:
	@echo "=== Installing dependencies ==="
	@if command -v dnf >/dev/null 2>&1; then \
		echo ">> Detected dnf (Amazon Linux 2023)"; \
		sudo dnf install -y git python3.11 python3.11-pip python3.11-devel gcc; \
	elif command -v yum >/dev/null 2>&1; then \
		echo ">> Detected yum (Amazon Linux 2)"; \
		sudo yum install -y git gcc; \
	fi
	@if command -v python3.11 >/dev/null 2>&1; then \
		echo ">> Python 3.11 found: $$(python3.11 --version)"; \
	else \
		echo ">> Python 3.11 not found — downloading standalone build..."; \
		curl -fSL -o /tmp/python3.11.tar.gz $(PYTHON_STANDALONE_URL) && \
		sudo tar xzf /tmp/python3.11.tar.gz -C /usr/local --strip-components=1 && \
		rm -f /tmp/python3.11.tar.gz && \
		echo ">> Installed: $$(python3.11 --version)"; \
	fi
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@if [ ! -f .env ]; then cp .env.example .env && echo "Created .env from .env.example"; fi
	sudo cp systemd/$(SERVICE).service /etc/systemd/system/
	sudo systemctl daemon-reload
	sudo systemctl enable $(SERVICE)
	@echo "=== Installation complete ==="
	@echo "Edit .env and run: make gen-keys && make run"

run:
	sudo systemctl start $(SERVICE)
	@echo "$(SERVICE) started"

stop:
	sudo systemctl stop $(SERVICE)
	@echo "$(SERVICE) stopped"

restart:
	sudo systemctl restart $(SERVICE)
	@echo "$(SERVICE) restarted"

update:
	@echo "=== Updating ==="
	git stash
	git pull --ff-only origin main || (echo "Pull failed" && git stash pop && exit 1)
	$(PIP) install -r requirements.txt
	@if $(MAKE) test; then \
		sudo systemctl restart $(SERVICE); \
		echo "=== Update complete ==="; \
	else \
		echo "Tests failed, rolling back..."; \
		git checkout @{1}; \
		$(PIP) install -r requirements.txt; \
		sudo systemctl restart $(SERVICE); \
		echo "=== Rolled back ==="; \
		exit 1; \
	fi

test:
	$(PYTEST) tests/ -v --tb=short

logs:
	journalctl -u $(SERVICE) -f

status:
	systemctl status $(SERVICE)

gen-keys:
	@echo "Generating new keys..."
	@MODEL_KEY=$$($(PYTHON) -c "import secrets; print(secrets.token_hex(32))") && \
		USER_KEY=$$($(PYTHON) -c "import secrets; print(secrets.token_hex(32))") && \
		PROXY_PASS=$$($(PYTHON) -c "import secrets; print(secrets.token_hex(16))") && \
		SECRET=$$($(PYTHON) -c "import secrets; print(secrets.token_hex(32))") && \
		sed -i "s|^MODEL_API_KEY=.*|MODEL_API_KEY=$$MODEL_KEY|" .env && \
		sed -i "s|^USER_API_KEY=.*|USER_API_KEY=$$USER_KEY|" .env && \
		sed -i "s|^PROXY_PASSWORD=.*|PROXY_PASSWORD=$$PROXY_PASS|" .env && \
		sed -i "s|^SECRET_KEY=.*|SECRET_KEY=$$SECRET|" .env && \
		echo "MODEL_API_KEY=$$MODEL_KEY" && \
		echo "USER_API_KEY=$$USER_KEY" && \
		echo "PROXY_PASSWORD=$$PROXY_PASS" && \
		echo "SECRET_KEY=$$SECRET" && \
		echo "Keys written to .env"

uninstall:
	sudo systemctl stop $(SERVICE) 2>/dev/null || true
	sudo systemctl disable $(SERVICE) 2>/dev/null || true
	sudo rm -f /etc/systemd/system/$(SERVICE).service
	sudo systemctl daemon-reload
	@echo "$(SERVICE) uninstalled"
