"""Direct AI provider and web-search desktop endpoints."""
from skillhub.infrastructure.ai_protocol import deepseek_options, ai_response_content


import time
from urllib.parse import urlparse

import requests
from ddgs import DDGS


class AiProviderApiMixin:
    """Expose configured AI provider operations."""

    def ai_test_connection(self, settings=None):
        """Test API connectivity with a minimal request."""
        settings = settings or {}
        if not isinstance(settings, dict):
            return {"error": "Invalid AI settings"}
        key = settings.get("api_key") or self.deepseek_api_key
        model = settings.get("model") or self.deepseek_model
        base = settings.get("api_base") or self.api_base
        if not all(isinstance(v, str) for v in (key, model, base)) or not base.startswith(("https://", "http://")):
            return {"error": "Invalid AI settings"}
        if not key:
            return {"error": "请先配置 API Key" if self.language == "zh" else "Please configure API Key first"}

        start = time.time()
        try:
            url = base.strip()
            if not url.endswith("/chat/completions"):
                url = url.rstrip("/") + "/chat/completions"
            resp = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "Hi"}],
                    "max_tokens": 256,
                    **({"thinking": {"type": "disabled"}} if urlparse(url).hostname == "api.deepseek.com" else {}),
                    "tools": [{"type": "function", "function": {"name": "connection_probe", "description": "Check tool support", "parameters": {"type": "object", "properties": {}}}}],
                    "tool_choice": {"type": "function", "function": {"name": "connection_probe"}}
                },
                timeout=15
            )
            elapsed = int((time.time() - start) * 1000)
            if resp.status_code == 200:
                calls = resp.json().get("choices", [{}])[0].get("message", {}).get("tool_calls", [])
                supported = any(c.get("function", {}).get("name") == "connection_probe" for c in calls)
                return {"ok": supported, "connected": True, "tool_calling": supported,
                        "error": "" if supported else "接口已连接，但未返回工具调用 / Connected, but tool calling was not verified",
                        "model": resp.json().get("model", model), "latency_ms": elapsed}
            else:
                try:
                    err = resp.json().get("error", {}).get("message", f"HTTP {resp.status_code}")
                except Exception:
                    err = resp.text or f"HTTP {resp.status_code}"
                return {"error": err}
        except requests.exceptions.Timeout:
            return {"error": "连接超时" if self.language == "zh" else "Connection timed out"}
        except Exception as e:
            return {"error": str(e)}

    def ai_web_search(self, query):
        """Search the web and return raw results for the chat context."""
        results = []
        try:
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=5):
                    results.append({
                        "title": r.get("title", ""),
                        "body": r.get("body", "")[:300],
                        "href": r.get("href", "")
                    })
        except Exception:
            pass
        return {"results": results}

    def ai_chat(self, messages, mode="chat"):
        """
        Chat with DeepSeek.
        mode='chat': conversational skill advisor.
        mode='generate': synthesize conversation into a skill .md file.
        Returns {reply, skill} for generate mode, {reply} for chat mode.
        """
        if not self.deepseek_api_key:
            return {"error": "请先配置 API Key" if self.language == "zh" else "Please configure API Key first"}

        lang = self.language

        if mode == "generate":
            system_prompt = f"""你是一位资深软件规范专家。根据对话历史，生成一份专业的 AI 开发技能指南（Markdown）。

严格按以下格式输出：

---frontmatter---
title: <技能标题>
emoji: <emoji>
tags: <3-5个标签>
description: <一句话描述>

## 🎯 核心规范
<至少3条具体规范>

## 📋 最佳实践
<具体建议>

## ⚠️ 注意事项
<需要警惕的问题>

输出语言：{'中文' if lang == 'zh' else 'English'}
只输出 markdown，别加多余解释。"""
        else:
            system_prompt = f"""你是一位资深的软件开发规范顾问。你的任务是和用户对话，帮他们理清需求，制定合适的 AI 开发技能指南。

对话风格：
- 先理解用户的项目背景和技术栈
- 如果需求模糊，主动提问澄清（一次最多问2个问题）
- 给出具体的规范建议，而不是空泛的理论
- 当用户觉得讨论充分了，告诉他们可以点击"生成技能"按钮

输出语言：{'中文' if lang == 'zh' else 'English'}
保持回复简洁，一次聚焦1-2个要点。"""

        try:
            url = self.api_base.strip()
            if not url.endswith("/chat/completions"):
                url = url.rstrip("/") + "/chat/completions"

            resp = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {self.deepseek_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.deepseek_model, **deepseek_options(self.api_base, getattr(self, "ai_reasoning_effort", "high")),
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        *messages
                    ],
                    "temperature": 0.7,
                    "max_tokens": 4096
                },
                timeout=90
            )
            if resp.status_code != 200:
                err = resp.json().get("error", {}).get("message", f"HTTP {resp.status_code}")
                return {"error": err}

            reply = ai_response_content(resp.json())

            if mode == "generate":
                parsed = self._parse_ai_skill(reply)
                return {"reply": reply, "skill": parsed}
            return {"reply": reply}

        except requests.exceptions.Timeout:
            return {"error": "请求超时" if lang == "zh" else "Request timed out"}
        except Exception as e:
            return {"error": str(e)}
