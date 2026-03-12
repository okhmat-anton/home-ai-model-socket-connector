SHELL := /bin/bash
.PHONY: install run stop restart update test logs status gen-keys uninstall

PYTHON := python3.11
VENV := venv
PIP := $(VENV)/bin/pip
PYTEST := $(VENV)/bin/pytest
SERVICE := home-ai-connector

install:
	@echo "=== Installing dependencies (Amazon Linux 2023) ==="
	sudo dnf install -y git python3.11 python3.11-pip python3.11-devel gcc
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
