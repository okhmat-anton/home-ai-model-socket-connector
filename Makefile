SHELL := /bin/bash
.PHONY: install run stop restart update test logs status gen-keys uninstall add-domain remove-domain

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
	@if command -v python3.11 >/dev/null 2>&1 && python3.11 -c 'import ssl' 2>/dev/null; then \
		echo ">> Python 3.11 found (with SSL): $$(python3.11 --version)"; \
	else \
		echo ">> Python 3.11 not found or missing SSL — downloading standalone build..."; \
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
	@PREV=$$(git rev-parse HEAD) && \
	git stash || true && \
	if git pull --ff-only origin main; then \
		$(PIP) install -r requirements.txt && \
		if $(MAKE) test; then \
			sudo systemctl restart $(SERVICE) && \
			echo "=== Update complete ==="; \
		else \
			echo "Tests failed, rolling back to $$PREV..." && \
			git reset --hard $$PREV && \
			$(PIP) install -r requirements.txt && \
			sudo systemctl restart $(SERVICE) && \
			echo "=== Rolled back ===" && \
			exit 1; \
		fi; \
	else \
		echo "Pull failed" && \
		git stash pop 2>/dev/null || true && \
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
		PROXY_USR=$$(grep '^PROXY_USER=' .env | cut -d= -f2) && \
		echo "" && \
		echo "MODEL_API_KEY=$$MODEL_KEY" && \
		echo "USER_API_KEY=$$USER_KEY" && \
		echo "SECRET_KEY=$$SECRET" && \
		echo "" && \
		echo "PROXY_USER=$$PROXY_USR" && \
		echo "PROXY_PASSWORD=$$PROXY_PASS" && \
		echo "Proxy URL: http://$$PROXY_USR:$$PROXY_PASS@<server-ip>:10667" && \
		echo "" && \
		echo "Keys written to .env"

uninstall:
	sudo systemctl stop $(SERVICE) 2>/dev/null || true
	sudo systemctl disable $(SERVICE) 2>/dev/null || true
	sudo rm -f /etc/systemd/system/$(SERVICE).service
	sudo systemctl daemon-reload
	@echo "$(SERVICE) uninstalled"

add-domain:
	@if [ -z "$(domain)" ]; then echo "Usage: make add-domain domain=example.com"; exit 1; fi
	@echo "=== Setting up HTTPS for $(domain) ==="
	@if ! command -v caddy >/dev/null 2>&1; then \
		echo ">> Installing Caddy..."; \
		sudo yum install -y yum-utils 2>/dev/null || true; \
		curl -fsSL https://getcaddy.com -o /tmp/getcaddy.sh && \
		chmod +x /tmp/getcaddy.sh && \
		sudo /tmp/getcaddy.sh || (\
			echo ">> Trying alternative install..."; \
			curl -fsSL -o /tmp/caddy.tar.gz https://github.com/caddyserver/caddy/releases/download/v2.8.4/caddy_2.8.4_linux_amd64.tar.gz && \
			sudo tar xzf /tmp/caddy.tar.gz -C /usr/local/bin caddy && \
			sudo chmod +x /usr/local/bin/caddy && \
			rm -f /tmp/caddy.tar.gz \
		); \
		rm -f /tmp/getcaddy.sh; \
	else \
		echo ">> Caddy already installed: $$(caddy version)"; \
	fi
	@echo ">> Writing Caddyfile..."
	@sudo mkdir -p /etc/caddy
	@echo '$(domain) {' | sudo tee /etc/caddy/Caddyfile > /dev/null
	@echo '    reverse_proxy localhost:10666' | sudo tee -a /etc/caddy/Caddyfile > /dev/null
	@echo '' | sudo tee -a /etc/caddy/Caddyfile > /dev/null
	@echo '    @websocket {' | sudo tee -a /etc/caddy/Caddyfile > /dev/null
	@echo '        header Connection *Upgrade*' | sudo tee -a /etc/caddy/Caddyfile > /dev/null
	@echo '        header Upgrade websocket' | sudo tee -a /etc/caddy/Caddyfile > /dev/null
	@echo '    }' | sudo tee -a /etc/caddy/Caddyfile > /dev/null
	@echo '    reverse_proxy @websocket localhost:10666' | sudo tee -a /etc/caddy/Caddyfile > /dev/null
	@echo '}' | sudo tee -a /etc/caddy/Caddyfile > /dev/null
	@echo ">> Setting up Caddy systemd service..."
	@sudo groupadd --system caddy 2>/dev/null || true
	@sudo useradd --system --gid caddy --create-home --home-dir /var/lib/caddy --shell /usr/sbin/nologin caddy 2>/dev/null || true
	@echo '[Unit]' | sudo tee /etc/systemd/system/caddy.service > /dev/null
	@echo 'Description=Caddy web server' | sudo tee -a /etc/systemd/system/caddy.service > /dev/null
	@echo 'After=network.target' | sudo tee -a /etc/systemd/system/caddy.service > /dev/null
	@echo '' | sudo tee -a /etc/systemd/system/caddy.service > /dev/null
	@echo '[Service]' | sudo tee -a /etc/systemd/system/caddy.service > /dev/null
	@echo 'User=caddy' | sudo tee -a /etc/systemd/system/caddy.service > /dev/null
	@echo 'Group=caddy' | sudo tee -a /etc/systemd/system/caddy.service > /dev/null
	@echo 'ExecStart=/usr/local/bin/caddy run --config /etc/caddy/Caddyfile' | sudo tee -a /etc/systemd/system/caddy.service > /dev/null
	@echo 'ExecReload=/usr/local/bin/caddy reload --config /etc/caddy/Caddyfile' | sudo tee -a /etc/systemd/system/caddy.service > /dev/null
	@echo 'Restart=on-failure' | sudo tee -a /etc/systemd/system/caddy.service > /dev/null
	@echo 'AmbientCapabilities=CAP_NET_BIND_SERVICE' | sudo tee -a /etc/systemd/system/caddy.service > /dev/null
	@echo '' | sudo tee -a /etc/systemd/system/caddy.service > /dev/null
	@echo '[Install]' | sudo tee -a /etc/systemd/system/caddy.service > /dev/null
	@echo 'WantedBy=multi-user.target' | sudo tee -a /etc/systemd/system/caddy.service > /dev/null
	sudo systemctl daemon-reload
	sudo systemctl enable caddy
	sudo systemctl restart caddy
	@echo "=== HTTPS active for $(domain) ==="
	@echo "SSL certificate will be auto-provisioned by Let's Encrypt."
	@echo "Make sure port 80 and 443 are open in your Lightsail firewall!"

remove-domain:
	@echo "=== Removing Caddy ==="
	sudo systemctl stop caddy 2>/dev/null || true
	sudo systemctl disable caddy 2>/dev/null || true
	sudo rm -f /etc/systemd/system/caddy.service
	sudo rm -rf /etc/caddy
	sudo systemctl daemon-reload
	@echo "Caddy removed"
