SHELL := /bin/bash
.PHONY: install run stop restart update test logs status gen-keys uninstall

PYTHON := python3.11
VENV := venv
PIP := $(VENV)/bin/pip
PYTEST := $(VENV)/bin/pytest
SERVICE := home-ai-connector

install:
	@echo "=== Installing dependencies (Amazon Linux 2) ==="
	sudo yum install -y git gcc openssl-devel bzip2-devel libffi-devel zlib-devel readline-devel sqlite-devel
	@if command -v python3.11 >/dev/null 2>&1; then \
		echo "Python 3.11 already installed"; \
	else \
		echo "Python 3.11 not found, installing from source (3-5 min)..."; \
		rm -rf /tmp/Python-3.11.11 /tmp/Python-3.11.11.tgz && \
		cd /tmp && \
		curl -O https://www.python.org/ftp/python/3.11.11/Python-3.11.11.tgz && \
		tar xzf Python-3.11.11.tgz && \
		cd Python-3.11.11 && \
		echo ">> Running ./configure ..." && \
		./configure --prefix=/usr/local && \
		echo ">> Compiling (this takes a few minutes) ..." && \
		make -j$$(nproc) && \
		echo ">> Installing ..." && \
		sudo make altinstall && \
		cd / && rm -rf /tmp/Python-3.11.11 /tmp/Python-3.11.11.tgz && \
		echo "Python 3.11 installed to /usr/local/bin/python3.11"; \
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
