"""Small provider-specific request options and strict text response handling."""
from urllib.parse import urlparse


def deepseek_options(base, effort="high"):
    if urlparse(base).hostname != "api.deepseek.com":
        return {}
    if effort == "none":
        return {"thinking": {"type": "disabled"}}
    return {"thinking": {"type": "enabled"}, "reasoning_effort": effort}


def ai_response_content(body):
    choice = body["choices"][0]
    if choice.get("finish_reason") == "length":
        raise ValueError("AI output was truncated; no changes were applied")
    content = choice["message"].get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("AI returned no usable content")
    return content
