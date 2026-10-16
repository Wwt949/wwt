"""文本嵌入层（Phase 1 · 向量检索的地基）。

三种后端，按可用性自动降级，接口完全一致：

  onnx  BGE-small-zh-v1.5 (ONNX, 512 维)  —— 默认，离线可用，CPU ~5ms/条
  api   OpenAI 兼容 /embeddings 接口      —— 设 LEGALASSIST_EMBED_MODE=api 启用
  hash  字符 n-gram 哈希向量（纯 numpy）   —— 零依赖兜底，保证服务永不因缺模型而挂

注意：hash 后端只是"把词面匹配搬进向量空间"，不具备真正的语义泛化能力，
仅用于模型缺失时的降级，不要拿它当作 Phase 1 的成果。
"""
import hashlib
import json
import math
import os
import threading
import time
import urllib.request

from . import config

DIM_ONNX = 512
DIM_API = None          # 运行时由接口返回决定
DIM_HASH = 512

# BGE 官方建议：检索场景下对「查询」加指令前缀，对「文档」不加。
# 实测对短查询的召回有明显帮助（长查询影响较小）。
QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："


# --------------------------------------------------------------------- 后端基类
class _Backend:
    name = "base"
    dim = 0

    def encode(self, texts, is_query=False):
        raise NotImplementedError


class OnnxBgeBackend(_Backend):
    """BGE-small-zh-v1.5 ONNX 推理：CLS pooling + L2 归一化。"""

    name = "onnx-bge-small-zh"

    def __init__(self, model_dir):
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer

        self.np = np
        onnx_path = os.path.join(model_dir, "onnx", "model.onnx")
        self.session = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
        self.tokenizer = Tokenizer.from_file(os.path.join(model_dir, "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=512)
        self.tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")

        self._input_names = {i.name for i in self.session.get_inputs()}
        self.dim = self.session.get_outputs()[0].shape[-1]
        self._lock = threading.Lock()          # onnxruntime session 非线程安全，串行化

    def encode(self, texts, is_query=False):
        if not texts:
            return self.np.zeros((0, self.dim), dtype="float32")
        payload = [QUERY_INSTRUCTION + t for t in texts] if is_query else list(texts)

        encs = self.tokenizer.encode_batch(payload)
        ids = self.np.array([e.ids for e in encs], dtype="int64")
        mask = self.np.array([e.attention_mask for e in encs], dtype="int64")

        feeds = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self._input_names:
            feeds["token_type_ids"] = self.np.zeros_like(ids)

        with self._lock:
            hidden = self.session.run(None, feeds)[0]

        cls = hidden[:, 0]                                    # CLS pooling（BGE 官方做法）
        return _l2_normalize(cls)


class ApiBackend(_Backend):
    """OpenAI 兼容的 /embeddings 接口（MoMA / DeepSeek / 智谱 / 通义 等）。"""

    name = "api-embedding"

    def __init__(self, base_url, api_key, model):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.dim = 0

    def encode(self, texts, is_query=False):
        import numpy as np

        body = json.dumps({"model": self.model, "input": list(texts)}).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + "/embeddings",
            data=body,
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + self.api_key},
        )
        with urllib.request.urlopen(req, timeout=config.LLM_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        vecs = [item["embedding"] for item in sorted(data["data"], key=lambda d: d["index"])]
        arr = np.array(vecs, dtype="float32")
        self.dim = arr.shape[1]
        return _l2_normalize(arr)


class HashBackend(_Backend):
    """零依赖兜底：字符 n-gram 哈希到固定维度。无语义泛化能力，仅保证可用性。"""

    name = "hash-fallback"
    dim = DIM_HASH

    def encode(self, texts, is_query=False):
        import numpy as np

        out = np.zeros((len(texts), self.dim), dtype="float32")
        for row, text in enumerate(texts):
            clean = "".join(ch for ch in text if not ch.isspace())
            grams = [clean[i:i + n] for n in (1, 2, 3) for i in range(max(0, len(clean) - n + 1))]
            for g in grams:
                h = int.from_bytes(hashlib.md5(g.encode("utf-8")).digest()[:8], "big")
                out[row, h % self.dim] += 1.0 / math.sqrt(len(grams) or 1)
        return _l2_normalize(out)


def _l2_normalize(arr):
    import numpy as np
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (arr / norms).astype("float32")


# ------------------------------------------------------------------------ 外观
class Embedder:
    """全局嵌入入口。所有检索都必须经由 encode()，便于统一替换后端与埋点。"""

    def __init__(self):
        self.backend = None
        self.fallback_reason = ""
        self.stats = {"calls": 0, "texts": 0, "total_ms": 0.0}
        self._load()

    def _load(self):
        mode = config.EMBED_MODE
        if mode in ("auto", "onnx"):
            model_dir = config.EMBED_MODEL_DIR
            if os.path.isfile(os.path.join(model_dir, "onnx", "model.onnx")):
                try:
                    self.backend = OnnxBgeBackend(model_dir)
                    return
                except Exception as exc:
                    self.fallback_reason = "ONNX 模型加载失败: %s" % exc
            else:
                self.fallback_reason = "未找到模型 %s（运行 python tools/fetch_model.py 下载）" % model_dir
            if mode == "onnx":
                raise RuntimeError(self.fallback_reason)

        if mode in ("auto", "api") and config.EMBED_API_KEY and config.EMBED_BASE_URL:
            try:
                self.backend = ApiBackend(config.EMBED_BASE_URL, config.EMBED_API_KEY, config.EMBED_MODEL)
                return
            except Exception as exc:
                self.fallback_reason = "API 嵌入初始化失败: %s" % exc

        self.backend = HashBackend()

    @property
    def name(self):
        return self.backend.name

    @property
    def dim(self):
        return int(self.backend.dim)

    @property
    def is_semantic(self):
        """是否为真正的语义嵌入（hash 兜底不算）。"""
        return self.backend.name != "hash-fallback"

    def encode(self, texts, is_query=False):
        if isinstance(texts, str):
            texts = [texts]
            single = True
        else:
            single = False
        started = time.time()
        vecs = self.backend.encode(texts, is_query=is_query)
        elapsed = (time.time() - started) * 1000
        self.stats["calls"] += 1
        self.stats["texts"] += len(texts)
        self.stats["total_ms"] += elapsed
        return vecs[0] if single else vecs

    def info(self):
        return {
            "backend": self.name,
            "dim": self.dim,
            "semantic": self.is_semantic,
            "fallback_reason": self.fallback_reason,
            "avg_ms": round(self.stats["total_ms"] / max(self.stats["calls"], 1), 2),
            "calls": self.stats["calls"],
            "texts_encoded": self.stats["texts"],
        }


EMBEDDER = Embedder()

