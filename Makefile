.PHONY: install test bench seed reset reset-dev migrate dev demo web
install:  ; cd apps/api && pip install -e '.[dev]'
test:     ; cd apps/api && python -m pytest -q
bench:    ; cd apps/api && python -m handshake.bench --json
migrate:  ; cd apps/api && alembic upgrade head
seed:     ; cd apps/api && python -m handshake.seed
reset:    ; cd apps/api && python -m handshake.seed --reset
reset-dev: ; cd apps/api && python -m handshake.seed --reset --dev-keys
demo:     ; cd apps/api && PYTHONPATH=. python scripts/demo_scenarios.py
dev:      ; cd apps/api && AUTO_CREATE_TABLES=1 uvicorn index:app --reload --port 8000
web: ; cd apps/web && npm run dev
