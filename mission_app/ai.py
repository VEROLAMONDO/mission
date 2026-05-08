"""Configurable AI text-processing client and local fallback task splitter."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .models import MINIMUM_TASK_MINUTES


@dataclass(frozen=True)
class AIConfig:
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    timeout_seconds: int = 30
    enabled: bool = False


class AIClient:
    """Small OpenAI-compatible JSON client used only through explicit app actions."""

    def __init__(self, config: AIConfig) -> None:
        self.config = config

    def generate_task_tree(self, goal: str, deadline: str = "", available_time: str = "") -> dict[str, Any]:
        prompt = (
            "请把目标拆分为多级任务树，最小任务约20分钟。"
            "返回JSON，字段包含title, estimatedMinutes, difficulty, children, acceptanceCriteria。\n"
            f"目标：{goal}\n截止日期：{deadline}\n可用时间：{available_time}"
        )
        if self.config.enabled and self.config.base_url:
            try:
                return self._chat_json(prompt)
            except (urllib.error.URLError, TimeoutError, ValueError, KeyError, json.JSONDecodeError):
                pass
        return local_task_tree(goal)

    def _chat_json(self, prompt: str) -> dict[str, Any]:
        url = self.config.base_url.rstrip("/")
        if not url.endswith("/chat/completions"):
            url = f"{url}/chat/completions"
        body = {
            "model": self.config.model or "local-model",
            "messages": [
                {"role": "system", "content": "你是任务拆分助手，只输出JSON。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {self.config.api_key}"} if self.config.api_key else {}),
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        content = payload["choices"][0]["message"]["content"]
        return json.loads(content)


def local_task_tree(goal: str) -> dict[str, Any]:
    """Return a deterministic offline task-tree draft when no AI service is configured."""
    clean_goal = goal.strip() or "未命名项目"
    stages = [
        ("明确范围与验收标准", ["写出目标定义", "列出完成标准", "确认时间预算"]),
        ("执行第一轮最小任务", ["收集资料", "完成核心动作", "记录问题"]),
        ("复盘并调整计划", ["整理输出物", "修正后续任务", "生成阶段总结"]),
    ]
    children: list[dict[str, Any]] = []
    for stage_title, tasks in stages:
        children.append(
            {
                "title": stage_title,
                "estimatedMinutes": len(tasks) * MINIMUM_TASK_MINUTES,
                "difficulty": 2,
                "children": [
                    {
                        "title": f"{task} 20分钟",
                        "estimatedMinutes": MINIMUM_TASK_MINUTES,
                        "difficulty": 1,
                        "acceptanceCriteria": ["完成该20分钟行动", "写下结果或问题"],
                    }
                    for task in tasks
                ],
            }
        )
    return {
        "title": clean_goal,
        "estimatedMinutes": sum(child["estimatedMinutes"] for child in children),
        "difficulty": 2,
        "children": children,
        "acceptanceCriteria": ["所有最小任务完成", "生成项目复盘记录"],
    }
