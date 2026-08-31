# Deploying CareerAgent to Amazon Bedrock AgentCore

This guide deploys the **evaluation core** (Strands agent + deterministic
matching) to Amazon Bedrock AgentCore Runtime using direct code
deployment. The FastAPI service and the persistence layer stay local —
that is the point of the separation:

```text
domain/core          app.service, app.matching, app.policy, app.schemas, app.resume_parser
      ↑
local runtime        FastAPI service (app.main) + UI + PostgreSQL persistence
      ↑
AgentCore runtime    app.agentcore_runtime (same core, AgentCore protocol)
```

The core is never modified for deployment and remains fully testable
locally (`make test`, `make run`).

## What gets deployed

The deployment package (`scripts/agentcore_deploy.py --package-only`)
contains only what the agent needs:

```text
main.py                       AgentCore entrypoint (boots agentcore_app)
requirements.txt              strands-agents, bedrock-agentcore, pydantic, pypdf, boto3
app/                          domain core + agentcore_runtime adapter
```

FastAPI, SQLAlchemy, Alembic and the web UI are deliberately excluded:
AgentCore Runtime exposes the evaluation capability, not the whole
service.

## Entrypoint contract

`POST /invocations` (the AgentCore protocol) receives a JSON payload:

```json
{"resume_text": "...", "job_description": "..."}
```

or a base64-encoded resume file:

```json
{"resume_b64": "<base64>", "resume_filename": "cv.pdf", "job_description": "..."}
```

and returns the `EvaluationResult` JSON (same schema as the `/api/v1`
API). Malformed payloads raise `ValueError`, which the runtime surfaces
as an error response with the exact message.

## Prerequisites

1. **AWS credentials** with permissions to create AgentCore runtimes,
   S3 buckets and pass the execution role
   (`aws sts get-caller-identity` must work).
2. **Execution role** (`AGENTCORE_ROLE_ARN`): trusted by
   `bedrock-agentcore.amazonaws.com`, allowing at minimum:
   - `bedrock:InvokeModel` on the Nova model you use
     (`BEDROCK_MODEL_ID`, default `amazon.nova-micro-v1:0`)
   - CloudWatch Logs writes (`logs:CreateLogStream`, `logs:PutLogEvents`)
   - S3 read access to the deployment bucket
   See [AgentCore runtime permissions](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-permissions.html).
   The AgentCore CLI can create this role for you (see alternative below).
3. **Bedrock model access** for Nova Micro enabled in the region.
4. Recent `boto3` (AgentCore control plane support).

## Test locally first (no AWS required)

```bash
make agentcore-run        # serves the AgentCore protocol on :8080
curl http://127.0.0.1:8080/ping
curl -X POST http://127.0.0.1:8080/invocations \
  -H 'content-type: application/json' \
  -d '{"resume_text": "Backend developer with 2 years of Python.", "job_description": "Requires Python and Docker for backend services."}'
```

`/ping` answers without any model call, so the protocol can be verified
with zero AWS dependencies.

## Deploy

```bash
make agentcore-zip        # dist/agentcore/career-agent-deployment_package.zip

AGENTCORE_ROLE_ARN=arn:aws:iam::<account>:role/<role> \
AWS_REGION=us-east-1 \
make agentcore-deploy
```

`scripts/agentcore_deploy.py` then:

1. resolves the account id with STS,
2. creates the code bucket if missing
   (`bedrock-agentcore-code-<account>-<region>`),
3. uploads the deployment package,
4. calls `CreateAgentRuntime` (or `UpdateAgentRuntime` if it exists) with
   runtime `PYTHON_3_13`, entrypoint `main.py`, public network and a
   5-minute idle timeout.

## Invoke the deployed agent

With the AgentCore CLI:

```bash
agentcore invoke --runtime career-agent \
  '{"resume_text": "Backend developer with 2 years of Python.", "job_description": "Requires Python and Docker."}'
```

Or with boto3 (data plane):

```python
import json, uuid, boto3

client = boto3.client("bedrock-agentcore")
response = client.invoke_agent_runtime(
    agentRuntimeArn="<ARN printed by the deploy script>",
    runtimeSessionId=str(uuid.uuid4()),
    payload=json.dumps({"resume_text": "...", "job_description": "..."}).encode(),
    qualifier="DEFAULT",
)
print(json.loads(b"".join(response["response"]).decode()))
```

## Observability and tracing

- Every invocation is logged by the runtime with a `requestId`; errors
  include error type, message and stack trace.
- Pipeline stage timings (`profile_extraction`, `requirements_extraction`,
  `deterministic_matching`, `career_plan`, `explanation`) are logged by
  `app.service` and land in the runtime's CloudWatch log group:
  `/aws/bedrock-agentcore/runtimes/<agent-id>-DEFAULT`.
- Enable **CloudWatch Transaction Search** for traces
  ([AgentCore observability](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability.html)),
  or use `agentcore logs` / `agentcore traces list` from the CLI.

## Sessions

Not used: one evaluation is a single-shot request with no conversational
state. AgentCore sessions would add cost without value here.

## Alternative: AgentCore CLI

If you prefer the managed flow (it also creates the execution role and
CloudFormation resources):

```bash
npm install -g @aws/agentcore
agentcore create --name career-agent --framework Strands --build CodeZip
# point the generated project at this repo's core,
# then: agentcore dev && agentcore deploy
```

See [Get started with the AgentCore CLI](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html).

## Clean up

```bash
# with the CLI project: agentcore remove all && agentcore deploy
# or delete the runtime directly (console / bedrock-agentcore-control DeleteAgentRuntime)
```

## Deployment attempt log (2026-09-01, v1.0)

The deployment was re-attempted with valid AWS credentials
(`aws sts get-caller-identity` → account `740055419949`, user `bedrook`,
shared credentials file). Result: **still blocked — IAM permissions**.
Every probe below was a read-only call; the exact errors:

| Command (boto3 equivalent) | AWS service | Error |
|---|---|---|
| `bedrock-agentcore-control.list_agent_runtimes()` | Bedrock AgentCore control plane | `AccessDeniedException` |
| `s3.list_buckets()` | S3 | `AccessDenied` |
| `bedrock-runtime.invoke_model(modelId="amazon.nova-micro-v1:0")` | Bedrock runtime | **OK** |
| `sts.get_caller_identity()` | STS | **OK** |

The IAM user has Bedrock model access (the local API and eval suite
run against Nova Micro with these credentials) but lacks
`bedrock-agentcore-control` and S3 permissions, which the direct code
deployment flow requires (S3 upload of the package +
`CreateAgentRuntime`). No execution role trusted by
`bedrock-agentcore.amazonaws.com` exists in the account either.

To unblock: grant the user `bedrock-agentcore-control` + S3 permissions
(or run `make agentcore-deploy` from a role that has them) and create
the execution role from [Prerequisites](#prerequisites). The deploy
itself is one command and was validated package-wise via
`make agentcore-zip`.
