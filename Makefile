.PHONY: install dev test lint format run cli demo-site demo-run demo-spa costs migrate docker-build docker-run compose-up compose-down agentcore-run agentcore-zip agentcore-deploy agentcore-role eval eval-llm benchmark benchmark-mock

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

demo-site:
	python scripts/demo_job_site.py

demo-run:
	python scripts/demo_job_site.py >/dev/null 2>&1 & \
	site_pid=$$!; \
	trap 'kill $$site_pid 2>/dev/null || true' EXIT; \
	sleep 1; \
	JOB_FETCH_ALLOW_PRIVATE_HOSTS=1 uvicorn app.main:app --reload

demo-spa:
	python scripts/demo_job_site.py >/dev/null 2>&1 & \
	site_pid=$$!; \
	trap 'kill $$site_pid 2>/dev/null || true' EXIT; \
	sleep 1; \
	JOB_FETCH_ALLOW_PRIVATE_HOSTS=1 python -m app.cli --job-url http://127.0.0.1:8001/jobs/spa-data-science.html

costs:
	python scripts/aws_costs.py

eval:
	python scripts/run_evals.py --tier deterministic

eval-llm:
	python scripts/run_evals.py --tier llm

benchmark:
	python scripts/benchmark.py

benchmark-mock:
	python scripts/benchmark.py --mock --count 10

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

agentcore-role:
	python scripts/agentcore_deploy.py --create-role

agentcore-deploy:
	python scripts/agentcore_deploy.py
