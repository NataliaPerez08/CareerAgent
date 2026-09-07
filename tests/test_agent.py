"""Structural tests for agent construction.

Day 2 of the sprint: the structured pipeline must not run tool loops.
These tests pin the shape of both agents without calling Bedrock:

- ``build_agent()`` keeps the five tools (demonstrable Strands workflow,
  used by ``CLI --chat`` and the evals tool-invocation metric).
- ``build_pipeline_agent()`` has no tools and a system prompt that never
  asks the model to calculate anything.
"""

from app import agent as agent_module


def _capture_agent_kwargs(monkeypatch) -> dict:
    captured: dict = {}

    def fake_agent(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(agent_module, "Agent", fake_agent)
    monkeypatch.setattr(agent_module, "BedrockModel", lambda **kwargs: object())
    return captured


def test_build_agent_keeps_the_five_demo_tools(monkeypatch):
    captured = _capture_agent_kwargs(monkeypatch)

    agent_module.build_agent()

    tools = [getattr(tool, "__name__", str(tool)) for tool in captured["tools"]]
    assert sorted(tools) == [
        "analyze_job",
        "calculate_match",
        "generate_interview_plan",
        "identify_skill_gaps",
        "normalize_skills",
    ]
    assert captured["system_prompt"] == agent_module.SYSTEM_PROMPT


def test_build_pipeline_agent_has_no_tools(monkeypatch):
    captured = _capture_agent_kwargs(monkeypatch)

    agent_module.build_pipeline_agent()

    assert captured["tools"] == []
    assert captured["system_prompt"] == agent_module.PIPELINE_SYSTEM_PROMPT


def test_pipeline_prompt_never_asks_the_model_to_calculate():
    prompt = agent_module.PIPELINE_SYSTEM_PROMPT

    # No tool workflow: the pipeline has no tools to call.
    for tool in (
        "analyze_job",
        "normalize_skills",
        "calculate_match",
        "identify_skill_gaps",
        "generate_interview_plan",
    ):
        assert tool not in prompt

    # The anti-hallucination discipline is preserved verbatim.
    assert "Never invent candidate experience." in prompt
    assert "Never infer that a requirement is optional, preferred," in prompt
    assert "Use evidence from the resume." in prompt
    assert "Never estimate match percentages, gap severity, or" in prompt


def test_both_agents_share_the_same_model_configuration(monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    monkeypatch.setenv("BEDROCK_TEMPERATURE", "0.1")

    seen: list[dict] = []

    def fake_model(**kwargs):
        seen.append(kwargs)
        return object()

    monkeypatch.setattr(agent_module, "BedrockModel", fake_model)
    monkeypatch.setattr(agent_module, "Agent", lambda **kwargs: object())

    agent_module.build_agent()
    agent_module.build_pipeline_agent()

    assert seen == [
        {"model_id": "amazon.nova-lite-v1:0", "region_name": "eu-west-1", "temperature": 0.1},
    ] * 2


def test_invalid_temperature_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("BEDROCK_TEMPERATURE", "not-a-number")

    seen: list[dict] = []
    monkeypatch.setattr(
        agent_module,
        "BedrockModel",
        lambda **kwargs: seen.append(kwargs) or object(),
    )
    monkeypatch.setattr(agent_module, "Agent", lambda **kwargs: object())

    agent_module.build_pipeline_agent()

    assert seen[0]["temperature"] == 0.2
