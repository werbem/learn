.PHONY: install dev start build test clean lint docker-up docker-down

# ── Installation ──
install:
	@echo "📦 Installing backend dependencies..."
	cd backend && pip install -r requirements.txt
	@echo "📦 Installing frontend dependencies..."
	cd frontend && pnpm install
	@echo "✅ All dependencies installed"

install-backend:
	cd backend && pip install -r requirements.txt

install-frontend:
	cd frontend && pnpm install

# ── Development ──
dev-backend:
	cd backend && python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

dev-frontend:
	cd frontend && pnpm dev

dev:
	@echo "🚀 Starting all services in dev mode..."
	@trap 'kill 0' EXIT; \
		$(MAKE) dev-backend & \
		$(MAKE) dev-frontend & \
		wait

# ── Production ──
start-backend:
	cd backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

start-frontend:
	cd frontend && pnpm start

start:
	@echo "🚀 Starting all services..."
	@trap 'kill 0' EXIT; \
		$(MAKE) start-backend & \
		$(MAKE) start-frontend & \
		wait

build:
	cd frontend && pnpm build

# ── Testing ──
test-backend:
	cd backend && python -m pytest tests/ -v

test:
	cd backend && python -m pytest tests/ -v

# ── Docker ──
docker-up:
	docker compose up --build -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

# ── Code Quality ──
lint:
	cd backend && python -m flake8 app/ tests/ 2>/dev/null || echo "flake8 not installed"
	cd frontend && pnpm lint 2>/dev/null || echo "No lint configured"

# ── Cleanup ──
clean:
	rm -rf frontend/.next frontend/node_modules
	find backend -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
	find . -type f -name "*.pyc" -delete
	rm -f data/*.db
	@echo "🧹 Clean complete"
