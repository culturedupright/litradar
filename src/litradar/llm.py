from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .config import USER_AGENT, detect_proxy

DEFAULT_BASE = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"
CREDENTIALS = Path.home() / ".dsh" / ".credentials.yaml"


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


def dsh_keys(path: Path | None = None) -> dict[str, str]:
    """从 DSH 凭据文件里读出可用 API Key，不打印、不写日志。"""
    path = path or CREDENTIALS
    if not path.exists():
        return {}
    keys: dict[str, str] = {}
    in_refs = False
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if re.match(r"^refs\s*:", line):
            in_refs = True
            continue
        if in_refs:
            if line and not line.startswith((" ", "\t")):
                break
            match = re.match(r"^\s+([A-Za-z0-9_]+)\s*:\s*(\S+)\s*$", line)
            if match:
                keys[match.group(1)] = match.group(2)
    return keys


def resolve_model(name: str = "deepseek") -> tuple[str, str, str]:
    """返回 (base_url, api_key, model)。优先环境变量，其次 DSH 凭据。"""
    keys = dsh_keys()
    base = os.environ.get("LITRADAR_API_BASE", DEFAULT_BASE)
    model = os.environ.get("LITRADAR_MODEL", DEFAULT_MODEL)
    api_key = os.environ.get("LITRADAR_API_KEY", "")

    if name == "deepseek":
        api_key = api_key or keys.get("DEEPSEEK_API_KEY", "")
        base = os.environ.get("LITRADAR_API_BASE", "https://api.deepseek.com/v1")
        model = os.environ.get("LITRADAR_MODEL", "deepseek-chat")
    elif name == "ling":
        api_key = api_key or keys.get("LING_API_KEY", "")
        base = os.environ.get("LITRADAR_API_BASE", "https://api.ling.ai/v1")
        model = os.environ.get("LITRADAR_MODEL", "ling-chat")
    else:
        api_key = api_key or keys.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise RuntimeError("没有找到可用 API Key：请设置 LITRADAR_API_KEY，或在 DSH 凭据里配置")
    return base.rstrip("/"), api_key, model


def _post(url: str, payload: dict, api_key: str, timeout: int = 120) -> dict:
    proxy = detect_proxy()
    handler = urllib.request.ProxyHandler(
        {"http": proxy, "https": proxy} if proxy else {}
    )
    opener = urllib.request.build_opener(handler)
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": USER_AGENT,
        },
    )
    with opener.open(request, timeout=timeout) as response:
        return json.loads(response.read())


def chat(messages: list[dict[str, str]], model_name: str = "deepseek",
         temperature: float = 0.2, retries: int = 3) -> tuple[str, Usage]:
    base, api_key, model = resolve_model(model_name)
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    last: Exception | None = None
    for attempt in range(retries):
        try:
            data = _post(f"{base}/chat/completions", payload, api_key)
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage") or {}
            return content, Usage(
                prompt_tokens=int(usage.get("prompt_tokens") or 0),
                completion_tokens=int(usage.get("completion_tokens") or 0),
                total_tokens=int(usage.get("total_tokens") or 0),
            )
        except Exception as exc:  # noqa: BLE001 - 限流/超时统一重试
            last = exc
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"模型调用失败：{last}")


def extract_json(text: str) -> dict:
    """从模型回复里取出 JSON，容忍 ```json 包裹和前后废话。"""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("模型回复里没有 JSON")
    return json.loads(text[start:end + 1])
