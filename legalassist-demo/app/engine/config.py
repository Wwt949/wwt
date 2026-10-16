"""全局配置：路径、模型路由表、演示数据开关。"""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
WEB_DIR = os.path.join(BASE_DIR, "web")
SESSION_DIR = os.path.join(DATA_DIR, "sessions")

# ---------------------------------------------------------------- 模型路由表
# 对应 PPT 第 7 页「MoMA 平台模型调用：多模型智能路由」。
# tier -> 该档位使用的模型、适用场景与延迟 SLA。
MODEL_TIERS = {
    "intent": {
        "model": "qwen-turbo",
        "label": "千问-Turbo",
        "scene": "意图识别 / 实体抽取 / 高频简单问题",
        "sla_ms": 500,
    },
    "dialogue": {
        "model": "glm-4",
        "label": "GLM-4（GLM-5.2）",
        "scene": "C 端日常咨询对话 / 结构化建议输出",
        "sla_ms": 3000,
    },
    "reasoning": {
        "model": "deepseek-v3",
        "label": "DeepSeek-V3",
        "scene": "复杂法律推理 / 长会话分析 / B 端意向分析报告",
        "sla_ms": 8000,
    },
}

# ------------------------------------------------------------ 真实模型接入开关
# 设置 LEGALASSIST_LLM=openai-compatible 并配置下面三项，即可从本地规则实现
# 切换到真实大模型（MoMA / DeepSeek / 智谱 / 通义 均提供 OpenAI 兼容端点）。
LLM_MODE = os.environ.get("LEGALASSIST_LLM", "mock")          # mock | openai-compatible
LLM_BASE_URL = os.environ.get("LEGALASSIST_BASE_URL", "")     # 例: https://api.moma.example/v1
LLM_API_KEY = os.environ.get("LEGALASSIST_API_KEY", "")
LLM_TIMEOUT = int(os.environ.get("LEGALASSIST_TIMEOUT", "60"))

# ------------------------------------------------------------------ 向量检索配置
# 嵌入后端：auto 自动探测（onnx -> api -> hash 兜底）| onnx | api | hash
EMBED_MODE = os.environ.get("LEGALASSIST_EMBED_MODE", "auto")
EMBED_MODEL_DIR = os.path.join(DATA_DIR, "models", "bge-small-zh-v1.5")
EMBED_API_KEY = os.environ.get("LEGALASSIST_EMBED_API_KEY", "")
EMBED_BASE_URL = os.environ.get("LEGALASSIST_EMBED_BASE_URL", "")
EMBED_MODEL = os.environ.get("LEGALASSIST_EMBED_MODEL", "bge-m3")

# 混合检索：稠密向量召回 + 词面召回，用 RRF 融合后再交给上层。
HYBRID_RETRIEVAL = os.environ.get("LEGALASSIST_HYBRID", "1") != "0"
RRF_K = 60                     # RRF 平滑常数，标准取值
RECALL_MULTIPLIER = 4          # 粗排召回 top_k * N，再精排截断

# RRF 通道权重。经典 RRF 取等权（1.0/1.0）。本场景一开始必须降词面通道的权
# 才能不掉分——但那是在补偿词面打分本身的缺陷（未做 IDF 加权、同分并列）。
# 修好 IDF 加权后，实测 0.5~1.0 全区间效果相当（44 题标注集差异 ≤1 题），
# 于是回归经典等权。由 tools/eval_retrieval.py --sweep 实测确认。
RRF_WEIGHT_DENSE = float(os.environ.get("LEGALASSIST_RRF_WDENSE", "1.0"))
RRF_WEIGHT_LEXICAL = float(os.environ.get("LEGALASSIST_RRF_WLEX", "1.0"))

# 多轮记忆管理：超过该轮数触发历史会话压缩（PPT 第 10 页策略四）。
MEMORY_COMPRESS_AFTER_TURNS = 10

# 回答兜底免责声明（PPT 第 6 页第 5 步「风险提示」）。
DISCLAIMER = (
    "以上内容由 AI 基于公开法条与示例案例自动生成，仅供参考，不构成正式法律意见。"
    "具体案件请结合完整证据材料咨询执业律师。"
)

