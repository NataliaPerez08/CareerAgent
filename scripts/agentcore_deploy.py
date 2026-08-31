"""Reproducible deployment of CareerAgent to Amazon Bedrock AgentCore Runtime.

Packages the domain core (no FastAPI, no persistence layer) into a
deployment zip, uploads it to S3 and creates or updates the AgentCore
Runtime — the "direct code deployment" flow from the AWS docs:

    https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-code-deploy-python.html

Usage:

    # build the deployment zip only (no AWS required)
    python scripts/agentcore_deploy.py --package-only

    # deploy (requires AWS credentials + an execution role)
    AGENTCORE_ROLE_ARN=arn:aws:iam::123456789012:role/AgentCoreRuntimeRole \
    python scripts/agentcore_deploy.py

See docs/deploy/agentcore.md for prerequisites, the execution role and
alternative deployment with the AgentCore CLI.
"""

import argparse
import json
import os
import zipfile
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "deploy" / "agentcore"
DIST = ROOT / "dist" / "agentcore"

DEFAULT_ROLE_NAME = "careeragent-agentcore-runtime"
ROLE_POLICY_NAME = "CareerAgentAgentCoreRuntimePolicy"

RUNTIME_CORE_MODULES = [
    "__init__.py",
    "agent.py",
    "agentcore_runtime.py",
    "career.py",
    "matching.py",
    "policy.py",
    "resume_parser.py",
    "schemas.py",
    "service.py",
    "tools.py",
]

RUNTIME = "PYTHON_3_13"
ENTRYPOINT = ["main.py"]
IDLE_TIMEOUT_SECONDS = 300
MAX_LIFETIME_SECONDS = 1800


def build_package(name: str) -> Path:
    """Build the deployment zip: core modules + entrypoint + requirements."""
    DIST.mkdir(parents=True, exist_ok=True)
    target = DIST / f"{name}-deployment_package.zip"

    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(STAGING / "main.py", "main.py")
        archive.write(STAGING / "requirements.txt", "requirements.txt")
        for module in RUNTIME_CORE_MODULES:
            archive.write(ROOT / "app" / module, f"app/{module}")

    included = zipfile.ZipFile(target).namelist()
    print(f"Package built: {target} ({target.stat().st_size} bytes, {len(included)} files)")
    return target


def _control_client(region: str):
    try:
        return boto3.client("bedrock-agentcore-control", region_name=region)
    except ValueError as exc:
        raise SystemExit(
            f"Could not create the bedrock-agentcore-control client: {exc}. "
            "Upgrade boto3 (pip install -U boto3) — AgentCore control plane "
            "support requires a recent version."
        ) from exc


def _artifact(bucket: str, name: str) -> dict:
    return {
        "codeConfiguration": {
            "code": {"s3": {"bucket": bucket, "prefix": f"{name}/deployment_package.zip"}},
            "runtime": RUNTIME,
            "entryPoint": ENTRYPOINT,
        }
    }


def _lifecycle() -> dict:
    return {
        "idleRuntimeSessionTimeout": IDLE_TIMEOUT_SECONDS,
        "maxLifetime": MAX_LIFETIME_SECONDS,
    }


def deploy(
    name: str,
    role_arn: str,
    region: str,
    bucket: str | None,
    package: Path,
) -> None:
    session = boto3.Session(region_name=region)
    account = session.client("sts").get_caller_identity()["Account"]
    bucket = bucket or f"bedrock-agentcore-code-{account}-{region}"
    key = f"{name}/deployment_package.zip"

    s3 = session.client("s3")
    try:
        s3.head_bucket(Bucket=bucket)
    except ClientError:
        location = {"LocationConstraint": region} if region != "us-east-1" else {}
        s3.create_bucket(Bucket=bucket, CreateBucketConfiguration=location)
        print(f"Created bucket: {bucket}")

    s3.upload_file(str(package), bucket, key)
    print(f"Uploaded: s3://{bucket}/{key}")

    client = _control_client(region)
    try:
        response = client.create_agent_runtime(
            agentRuntimeName=name,
            agentRuntimeArtifact=_artifact(bucket, name),
            networkConfiguration={"networkMode": "PUBLIC"},
            roleArn=role_arn,
            lifecycleConfiguration=_lifecycle(),
        )
        action = "Created"
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") not in {
            "ConflictException",
            "ResourceInUseException",
        }:
            raise
        response = client.update_agent_runtime(
            agentRuntimeIdentifier=name,
            agentRuntimeArtifact=_artifact(bucket, name),
            roleArn=role_arn,
            lifecycleConfiguration=_lifecycle(),
        )
        action = "Updated"

    runtime_arn = response.get("agentRuntime", {}).get("agentRuntimeArn") or response.get(
        "agentRuntimeArn", ""
    )
    print(f"{action} AgentCore Runtime: {name}")
    print(f"ARN: {runtime_arn}")
    print(
        "Invoke it with:\n"
        f"  agentcore invoke --runtime {name} "
        '\'{"resume_text": "...", "job_description": "..."}\'\n'
        "or with boto3 (bedrock-agentcore data plane, InvokeAgentRuntime) — "
        "see docs/deploy/agentcore.md"
    )


def runtime_role_trust_policy() -> dict:
    """Trust policy: only the AgentCore service may assume this role."""
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "TrustBedrockAgentCore",
                "Effect": "Allow",
                "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }
        ],
    }


def runtime_role_policy(account: str, region: str, model_id: str) -> dict:
    """Least-privilege permissions for the runtime execution role.

    Exactly what docs/deploy/agentcore.md Prerequisites documents:
    invoke the one Bedrock model used, write AgentCore logs, read the
    deployment package from the code bucket. Nothing else.
    """
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "InvokeBedrockModel",
                "Effect": "Allow",
                "Action": "bedrock:InvokeModel",
                "Resource": f"arn:aws:bedrock:{region}::foundation-model/{model_id}",
            },
            {
                "Sid": "AgentCoreCloudWatchLogs",
                "Effect": "Allow",
                "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
                "Resource": "arn:aws:logs:*:*:log-group:/aws/bedrock-agentcore*",
            },
            {
                "Sid": "ReadDeploymentPackage",
                "Effect": "Allow",
                "Action": "s3:GetObject",
                "Resource": f"arn:aws:s3:::bedrock-agentcore-code-{account}-{region}/*",
            },
        ],
    }


def create_runtime_role(region: str, model_id: str, role_name: str) -> str:
    """Create (or refresh) the least-privilege execution role. Idempotent.

    Requires the caller to have iam:CreateRole and iam:PutRolePolicy
    (option 1 in docs/deploy/agentcore.md). Returns the role ARN.
    """
    session = boto3.Session(region_name=region)
    iam = session.client("iam")
    account = session.client("sts").get_caller_identity()["Account"]

    denied_hint = (
        "IAM denied this operation. The admin grant from "
        "docs/deploy/agentcore.md § Option 1, ready to run "
        "(iam:CreateRole + iam:PutRolePolicy + iam:PassRole) is required first."
    )
    try:
        response = iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(runtime_role_trust_policy()),
        )
        print(f"Created role: {response['Role']['Arn']}")
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code == "EntityAlreadyExistsException":
            print(f"Role already exists: arn:aws:iam::{account}:role/{role_name}")
        elif code in ("AccessDenied", "AccessDeniedException"):
            raise SystemExit(f"iam:CreateRole: {exc}\n{denied_hint}") from exc
        else:
            raise
    try:
        iam.put_role_policy(
            RoleName=role_name,
            PolicyName=ROLE_POLICY_NAME,
            PolicyDocument=json.dumps(runtime_role_policy(account, region, model_id)),
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("AccessDenied", "AccessDeniedException"):
            raise SystemExit(f"iam:PutRolePolicy: {exc}\n{denied_hint}") from exc
        raise
    print(
        f"Attached {ROLE_POLICY_NAME}: bedrock:InvokeModel on {model_id}, "
        "AgentCore log writes, deployment-package read"
    )
    role_arn = f"arn:aws:iam::{account}:role/{role_name}"
    print(
        "Deploy with:\n"
        f"  AGENTCORE_ROLE_ARN={role_arn} make agentcore-deploy"
    )
    return role_arn


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="career-agent", help="AgentCore Runtime name")
    parser.add_argument(
        "--role-arn",
        default=None,
        help="Execution role ARN (or AGENTCORE_ROLE_ARN env var; required to deploy)",
    )
    parser.add_argument("--region", default=None, help="AWS region (or AWS_REGION env var)")
    parser.add_argument("--bucket", default=None, help="S3 bucket for the deployment package")
    parser.add_argument(
        "--package-only",
        action="store_true",
        help="Only build the deployment zip under dist/agentcore/ (no AWS calls)",
    )
    parser.add_argument(
        "--create-role",
        action="store_true",
        help=(
            "Create/refresh the least-privilege execution role "
            f"(default name: {DEFAULT_ROLE_NAME}) and exit without deploying. "
            "Requires iam:CreateRole + iam:PutRolePolicy."
        ),
    )
    parser.add_argument(
        "--role-name",
        default=DEFAULT_ROLE_NAME,
        help=f"Execution role name for --create-role (default: {DEFAULT_ROLE_NAME})",
    )
    args = parser.parse_args()

    region = args.region or os.getenv("AWS_REGION", "us-east-1")
    model_id = os.getenv("BEDROCK_MODEL_ID", "amazon.nova-micro-v1:0")

    if args.create_role:
        create_runtime_role(region, model_id, args.role_name)
        return

    package = build_package(args.name)
    if args.package_only:
        return

    role_arn = args.role_arn or os.getenv("AGENTCORE_ROLE_ARN")
    if not role_arn:
        raise SystemExit(
            "Deploying requires an execution role. Pass --role-arn or set "
            "AGENTCORE_ROLE_ARN (see docs/deploy/agentcore.md)."
        )

    deploy(args.name, role_arn, region, args.bucket, package)


if __name__ == "__main__":
    main()
