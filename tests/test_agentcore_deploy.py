import json

from scripts.agentcore_deploy import (
    DEFAULT_ROLE_NAME,
    ROLE_POLICY_NAME,
    runtime_role_policy,
    runtime_role_trust_policy,
)

ACCOUNT = "123456789012"
REGION = "us-east-1"
MODEL = "amazon.nova-micro-v1:0"


def by_sid(policy, sid):
    return next(s for s in policy["Statement"] if s["Sid"] == sid)


def test_trust_policy_only_allows_agentcore_service():
    trust = runtime_role_trust_policy()
    assert trust["Version"] == "2012-10-17"
    assert len(trust["Statement"]) == 1
    statement = trust["Statement"][0]
    assert statement["Principal"] == {"Service": "bedrock-agentcore.amazonaws.com"}
    assert statement["Action"] == "sts:AssumeRole"
    assert statement["Effect"] == "Allow"


def test_role_policy_invokes_exactly_one_model():
    policy = runtime_role_policy(ACCOUNT, REGION, MODEL)
    invoke = by_sid(policy, "InvokeBedrockModel")
    assert invoke["Action"] == "bedrock:InvokeModel"
    assert invoke["Resource"] == f"arn:aws:bedrock:{REGION}::foundation-model/{MODEL}"
    assert invoke["Resource"].count("foundation-model") == 1


def test_role_policy_logs_scoped_to_agentcore_groups():
    policy = runtime_role_policy(ACCOUNT, REGION, MODEL)
    logs = by_sid(policy, "AgentCoreCloudWatchLogs")
    assert sorted(logs["Action"]) == ["logs:CreateLogStream", "logs:PutLogEvents"]
    assert logs["Resource"] == "arn:aws:logs:*:*:log-group:/aws/bedrock-agentcore*"


def test_role_policy_reads_only_the_code_bucket():
    policy = runtime_role_policy(ACCOUNT, REGION, MODEL)
    s3 = by_sid(policy, "ReadDeploymentPackage")
    assert s3["Action"] == "s3:GetObject"
    assert s3["Resource"] == f"arn:aws:s3:::bedrock-agentcore-code-{ACCOUNT}-{REGION}/*"


def test_role_policy_grants_nothing_else():
    policy = runtime_role_policy(ACCOUNT, REGION, MODEL)
    actions = {a for s in policy["Statement"] for a in ([s["Action"]] if isinstance(s["Action"], str) else s["Action"])}
    assert actions == {"bedrock:InvokeModel", "logs:CreateLogStream", "logs:PutLogEvents", "s3:GetObject"}


def test_policies_serialize_to_valid_json():
    json.dumps(runtime_role_trust_policy())
    json.dumps(runtime_role_policy(ACCOUNT, REGION, MODEL))


def test_role_naming_constants_are_stable():
    assert DEFAULT_ROLE_NAME == "careeragent-agentcore-runtime"
    assert ROLE_POLICY_NAME == "CareerAgentAgentCoreRuntimePolicy"
