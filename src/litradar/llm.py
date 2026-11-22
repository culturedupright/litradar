from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import USER_AGENT, detect_proxy

DEFAULT_BASE = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-flash"
CREDENTIALS = Path.home() / ".dsh" / ".credentials.yaml"

# 界面想知道“模型请求正在进行”，这里挂一个回调；失败、重试都会报出来。
_activity: "Callable[[str], None] | None" = None


def set_activity(fn=None) -> None:
    global _activity
    _activity = fn


def _note(text: str) -> None:
    if _activity is None:
        return
    try:
        _activity(text)
    except Exception:  # noqa: BLE001 - 上报失败不能影响流水线
        pass


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
    """返回 (base_url, api_key, model)。

    具体模型 id（例如 `deepseek-v4-pro`、`Ling-3.0-flash`）交给 DSH 配置发现层解析，
    这样面板选什么、请求就发到对应的 provider，而不是一律打到 DeepSeek。
    """
    keys = dsh_keys()
    env_key = os.environ.get("LITRADAR_API_KEY", "")
    env_base = os.environ.get("LITRADAR_API_BASE", "")
    env_model = os.environ.get("LITRADAR_MODEL", "")

    if name in ("", "deepseek", "ling"):
        if name == "ling":
            base = env_base or "https://api.ant-ling.com/v1"
            model = env_model or "Ling-3.0-flash"
            api_key = env_key or keys.get("LING_API_KEY", "")
        else:
            base = env_base or DEFAULT_BASE
            model = env_model or DEFAULT_MODEL
            api_key = env_key or keys.get("DEEPSEEK_API_KEY", "")
    else:
        from .model_catalog import find  # 延迟导入，避免与发现模块互相引用

        entry = find(name)
        if entry is None:
            base = env_base or DEFAULT_BASE
            model = env_model or name
            api_key = env_key or keys.get("DEEPSEEK_API_KEY", "")
        else:
            provider = entry["provider"]
            base = env_base or provider.get("baseURL") or DEFAULT_BASE
            model = env_model or entry["id"]
            env_name = provider.get("apiKeyEnv") or ""
            api_key = env_key or (keys.get(env_name, "") if env_name else "") or keys.get(
                "DEEPSEEK_API_KEY", ""
            )
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
    prompt_chars = sum(len(m.get("content") or "") for m in messages)
    last: Exception | None = None
    for attempt in range(retries):
        _note(f"→ {model} 发起请求（第 {attempt + 1}/{retries} 次，输入约 {prompt_chars} 字）")
        began = time.time()
        try:
            data = _post(f"{base}/chat/completions", payload, api_key)
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage") or {}
            result = Usage(
                prompt_tokens=int(usage.get("prompt_tokens") or 0),
                completion_tokens=int(usage.get("completion_tokens") or 0),
                total_tokens=int(usage.get("total_tokens") or 0),
            )
            _note(f"✓ {model} 返回 {result.total_tokens} tokens，耗时 {time.time() - began:.1f}s")
            return content, result
        except Exception as exc:  # noqa: BLE001 - 限流/超时统一重试
            last = exc
            wait = 2 * (attempt + 1)
            _note(f"× {type(exc).__name__}：{str(exc)[:80]}；{wait}s 后重试")
            time.sleep(wait)
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
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        # 模型常把换行直接写进字符串；strict=False 允许未转义控制字符
        return json.loads(text[start:end + 1], strict=False)
