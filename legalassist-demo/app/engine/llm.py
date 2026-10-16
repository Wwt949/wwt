"""MoMA 多模型智能路由（对应 PPT 第 7 页）。

路由策略：根据 任务类型 / 上下文长度 / 复杂度 选择最优模型档位。
  - 意图识别          -> 千问-Turbo   (延迟优先，成本最低)
  - 常规对话          -> GLM-4        (均衡)
  - 复杂推理/长文本   -> DeepSeek-V3  (效果优先)

默认 mock 模式：不联网，返回由本地规则引擎产生的结构化文本，
保证 demo 在无 API Key 的环境下也能端到端跑通。
配置 LEGALASSIST_LLM=openai-compatible 后自动切换为真实大模型调用。
"""
import json
import time
import urllib.request

from . import config


def route(task, prompt_len=0, complexity=0):
    """决定该请求走哪个模型档位，并返回路由理由（demo 中会在界面上展示）。"""
    if task == "intent":
        return "intent", "任务类型=意图识别，优先延迟与成本"
    if task == "lead_analysis":
        return "reasoning", "任务类型=B 端意向分析，需长文本理解与推理"
    if prompt_len > 1200 or complexity >= 3:
        return "reasoning", "上下文 %d 字 / 复杂度 %d，超出常规档位上限" % (prompt_len, complexity)
    return "dialogue", "常规咨询对话，均衡档位"


class LLMClient:
    """统一模型调用入口。所有 AI 能力都必须经由此处，便于埋点与成本核算。"""

    def __init__(self):
        self.mode = config.LLM_MODE
        self.base_url = config.LLM_BASE_URL.rstrip("/")
        self.api_key = config.LLM_API_KEY
        self.call_log = []          # 调用流水，供效果评估页展示

    # ---------------------------------------------------------------- 核心调用
    def complete(self, task, prompt, mock_text, prompt_len=None, complexity=0):
        """返回 (文本, 元信息)。mock 模式下直接返回本地规则引擎的结果。"""
        tier_key, reason = route(task, prompt_len if prompt_len is not None else len(prompt), complexity)
        tier = config.MODEL_TIERS[tier_key]
        started = time.time()

        if self.mode == "openai-compatible" and self.base_url and self.api_key:
            try:
                text = self._call_remote(tier["model"], prompt)
                provider = "remote"
            except Exception as exc:                      # 远程失败自动降级，保证可用性
                text = mock_text
                provider = "fallback(%s)" % type(exc).__name__
        else:
            text = mock_text
            provider = "local-rule-engine"

        latency_ms = int((time.time() - started) * 1000)
        meta = {
            "tier": tier_key,
            "model": tier["model"],
            "model_label": tier["label"],
            "scene": tier["scene"],
            "route_reason": reason,
            "provider": provider,
            "latency_ms": latency_ms,
            "sla_ms": tier["sla_ms"],
            "sla_ok": latency_ms <= tier["sla_ms"] or provider == "local-rule-engine",
            "prompt_chars": len(prompt),
            "output_chars": len(text),
        }
        self.call_log.append({"task": task, **meta})
        return text, meta

    # ------------------------------------------------------------ OpenAI 兼容
    def _call_remote(self, model, prompt):
        payload = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": "你是「智能律询通」的资深法律顾问助手。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + self.api_key,
            },
        )
        with urllib.request.urlopen(req, timeout=config.LLM_TIMEOUT) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return body["choices"][0]["message"]["content"]

    # ---------------------------------------------------------------- 路由统计
    def routing_stats(self):
        stats = {}
        for call in self.call_log:
            row = stats.setdefault(call["model_label"], {"calls": 0, "total_ms": 0})
            row["calls"] += 1
            row["total_ms"] += call["latency_ms"]
        for row in stats.values():
            row["avg_ms"] = int(row["total_ms"] / row["calls"])
        return stats


CLIENT = LLMClient()

