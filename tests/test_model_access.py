from chakshu.services.model_access import choose


def test_api_key_wins_over_a_subscription_token():
    access = choose("sk-ant-api-key", "sk-ant-oat-token", environ={})
    assert access.kind == "api_key"
    assert access.env == {"ANTHROPIC_API_KEY": "sk-ant-api-key"}


def test_subscription_token_alone():
    access = choose(None, "sk-ant-oat-token", environ={})
    assert access.kind == "subscription"
    assert access.env == {"CLAUDE_CODE_OAUTH_TOKEN": "sk-ant-oat-token"}


def test_container_environment_as_fallback():
    assert choose(None, None, environ={"CLAUDE_CODE_OAUTH_TOKEN": "x"}).kind == "environment"
    assert choose(None, None, environ={"CLAUDE_CODE_USE_BEDROCK": "1"}).kind == "environment"
    assert choose(None, None, environ={}).kind == "none"
