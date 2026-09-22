"""AI-assisted Skill search, parsing, and save endpoints."""

import os
from skillhub.domain.naming import is_project_rules_document
import re

import requests
from ddgs import DDGS

from skillhub.domain.naming import normalize_skill_filename
from skillhub.infrastructure.filesystem import safe_child_path


class AiSkillsApiMixin:
    """Expose AI-assisted Skill discovery and authoring."""

    def ai_search_skill(self, query):
        """
        Search the web for relevant skill guidelines, then use DeepSeek
        to synthesize a complete skill .md file from the search results.
        Returns {phase, title, emoji, tags, description, content} or {error}.
        """
        if not self.deepseek_api_key:
            return {"error": "请先在系统设置中配置 DeepSeek API Key" if self.language == "zh" else "Please configure your DeepSeek API Key in Settings first"}

        lang = self.language
        lang_hint = "中文" if lang == "zh" else "English"

        # ── Phase 1: Web Search ──
        search_results = []
        try:
            with DDGS() as ddgs:
                # Search for relevant skill guidelines
                search_query = f"site:github.com OR site:dev.to OR site:medium.com {query} guidelines best practices"
                results = list(ddgs.text(search_query, max_results=5))
                for r in results:
                    search_results.append({
                        "title": r.get("title", ""),
                        "body": r.get("body", "")[:300],
                        "href": r.get("href", "")
                    })
        except Exception as e:
            # If search fails, still try AI generation without search context
            search_results = []

        # ── Phase 2: AI Generation ──
        search_context = ""
        if search_results:
            search_context = "\n\n".join([
                f"### {r['title']}\n{r['body']}\nSource: {r['href']}"
                for r in search_results
            ])
        else:
            search_context = "（未找到相关搜索结果，请基于你的知识生成）" if lang == "zh" else "(No search results found, please generate based on your knowledge)"

        system_prompt = f"""你是一位资深的软件开发规范专家。你的任务是根据用户的描述，生成一份专业、实用的 AI 开发技能指南（Markdown 格式）。

输出必须严格按以下格式：

---frontmatter---
title: <简洁的技能标题>
emoji: <一个最贴切的emoji>
tags: <3-5个分类标签，逗号分隔>
description: <一句话描述这个技能的用途>

## 🎯 核心规范
<具体的开发指南、规范条目，至少3条，用markdown列表>

## 📋 最佳实践
<建议和技巧>

## ⚠️ 注意事项
<需要特别警惕的问题>

要求：
- 输出语言：{lang_hint}
- 内容要具体、可执行，不要空泛的理论
- 如果搜索结果中有参考内容，融入其中
- 格式干净，不输出多余的解释"""

        user_prompt = f"""用户需求：{query}

以下是在线搜索结果（供参考）：

{search_context}

请根据以上信息，生成一份完整的技能规范文件。只输出 markdown 内容。"""

        try:
            url = self.api_base.strip()
            if not url.endswith("/chat/completions"):
                url = url.rstrip("/") + "/chat/completions"

            response = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {self.deepseek_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.deepseek_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 4096
                },
                timeout=60
            )
            if response.status_code != 200:
                error_msg = response.json().get("error", {}).get("message", response.text)
                return {"error": f"DeepSeek API 错误: {error_msg}"}

            ai_content = response.json()["choices"][0]["message"]["content"]

            # Parse AI output
            parsed = self._parse_ai_skill(ai_content)
            return {
                "phase": "done",
                "title": parsed["title"],
                "emoji": parsed["emoji"],
                "tags": parsed["tags"],
                "description": parsed["description"],
                "content": parsed["content"]
            }

        except requests.exceptions.Timeout:
            return {"error": "AI 请求超时，请重试" if lang == "zh" else "AI request timed out, please retry"}
        except Exception as e:
            return {"error": str(e)}

    def _parse_ai_skill(self, raw_text):
        """Parse AI-generated markdown into structured skill data."""
        content = raw_text.strip()
        title = "AI 生成技能" if self.language == "zh" else "AI Generated Skill"
        emoji = "🤖"
        tags = ["AI生成"] if self.language == "zh" else ["AI-Generated"]
        description = ""

        # Try to parse frontmatter block
        fm_match = re.match(r'---frontmatter---\s*\n(.*?)\n---', content, re.DOTALL)
        if fm_match:
            fm_text = fm_match.group(1)
            for line in fm_text.splitlines():
                line = line.strip()
                if line.startswith("title:"):
                    title = line.split(":", 1)[1].strip()
                elif line.startswith("emoji:"):
                    emoji = line.split(":", 1)[1].strip()
                elif line.startswith("tags:"):
                    tags = [t.strip() for t in line.split(":", 1)[1].split(",") if t.strip()]
                elif line.startswith("description:"):
                    description = line.split(":", 1)[1].strip()
            # Remove frontmatter block from content, keep the rest as body
            content = content[fm_match.end():].strip()
        else:
            # Fallback: extract first h1 as title, first paragraph as description
            lines = content.splitlines()
            for line in lines:
                s = line.strip()
                if s.startswith("# "):
                    title = s.lstrip("#").strip()
                    break
            # Use first non-empty paragraph after title as description
            found_title = False
            for line in lines:
                s = line.strip()
                if not s:
                    continue
                if s.startswith("# ") and not found_title:
                    found_title = True
                    continue
                if found_title and not s.startswith("#"):
                    description = s[:200]
                    break

        return {
            "title": title,
            "emoji": emoji,
            "tags": tags[:6],
            "description": description,
            "content": content
        }

    def ai_save_skill(self, skill_data):
        """Save an AI-generated skill to the global library."""
        filename = normalize_skill_filename(skill_data.get("filename", ""), ensure_md=True)
        if is_project_rules_document(filename):
            return {"error": "AGENTS.md 不允许自动 AI 修改；请在项目规约编辑器手动编辑或单独授权 AI 起草。"}
        content = skill_data.get("content", "")
        if not filename or not content:
            return {"error": "Missing filename or content"}

        fp = safe_child_path(self.skills_dir, filename)
        if not fp:
            return {"error": "Invalid filename"}
        # If exists, append a numeric suffix
        if os.path.exists(fp):
            base = filename[:-3] if filename.lower().endswith(".md") else filename
            counter = 1
            while os.path.exists(fp):
                filename = f"{base}_{counter}.md"
                fp = safe_child_path(self.skills_dir, filename)
                if not fp:
                    return {"error": "Invalid filename"}
                counter += 1

        try:
            os.makedirs(self.skills_dir, exist_ok=True)
            with open(fp, "w", encoding="utf-8") as f:
                f.write(content)
            self._register_library_entry(filename, source="ai-generated")
            return {"ok": True, "filename": filename}
        except Exception as e:
            return {"error": str(e)}
