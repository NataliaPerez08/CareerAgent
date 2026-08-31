.PHONY: install dev test lint format run cli costs migrate docker-build docker-run compose-up compose-down agentcore-run agentcore-zip agentcore-deploy

install:
	python -m pip install -e .

dev:
	python -m pip install -e '.[dev]'

test:
	pytest -q

lint:
	ruff check .

format:
	ruff format .

run:
	uvicorn app.main:app --reload

migrate:
	alembic upgrade head

cli:
	python -m app.cli

costs:
	python scripts/aws_costs.py

docker-build:
	docker build -t career-agent:dev .

docker-run:
	docker run --rm -p 8000:8000 -e AWS_REGION=$${AWS_REGION:-us-east-1} career-agent:dev

compose-up:
	docker compose up --build -d

compose-down:
	docker compose down

agentcore-run:
	python -m app.agentcore_runtime

agentcore-zip:
	python scripts/agentcore_deploy.py --package-only

agentcore-deploy:
	python scripts/agentcore_deploy.py
