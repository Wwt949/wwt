"""向量索引：把法条 / 案例编码成稠密向量，做余弦相似度 Top-K 检索。

生产环境这一步对应 Milvus / pgvector / FAISS。这里用 numpy 暴力检索：
885 条 × 512 维全量打分约 0.2ms，比引入向量库依赖划算得多。
数据量涨到十万级时换 ANN 索引即可，本模块对外接口不需要变。

向量落盘缓存到 app/data/index_cache/，key 由「语料内容指纹 + 后端 + 维度」
共同决定：语料改了、模型换了都会自动失效重建，不会出现新旧向量混用。
"""
import hashlib
import os
import threading
import time

from . import config
from .embed import EMBEDDER

CACHE_DIR = os.path.join(config.DATA_DIR, "index_cache")
BATCH = 64                      # 分批编码，避免一次性占用过多内存


class VectorIndex:
    """一个语料集合对应一个索引实例。"""

    def __init__(self, name):
        self.name = name
        self.entries = []
        self.matrix = None          # (N, dim) float32，已 L2 归一化
        self.ids = []
        self.dim = 0
        self.built_at = ""
        self.from_cache = False
        self._lock = threading.Lock()

    # ------------------------------------------------------------ 构建 / 缓存
    def _fingerprint(self):
        """语料指纹：只要条目内容有任何一个字节变化，指纹就变。

        用编码后的文本（而非原 dict）算指纹，保证「换了 doc 拼接方式」也算变更。
        """
        h = hashlib.sha1()
        h.update(EMBEDDER.name.encode("utf-8"))
        h.update(str(EMBEDDER.dim).encode("utf-8"))
        h.update(self.name.encode("utf-8"))
        for entry_id, doc in self._docs:
            h.update(entry_id.encode("utf-8"))
            h.update(b"\x1f")
            h.update(doc.encode("utf-8"))
            h.update(b"\x1e")
        return h.hexdigest()[:16]

    def _cache_file(self):
        return os.path.join(CACHE_DIR, "%s-%s.npz" % (self.name, self._fingerprint()))

    @staticmethod
    def _encode_batched(docs):
        """按长度排序后分批编码：同一批内长度接近，padding 浪费最小。

        法条长短悬殊（13~392 字）。若 885 条一次性 padding 到最长，实际参与
        计算的 token 数会放大近十倍——实测建库从 110s 降到个位数秒。
        """
        import numpy as np
        out = np.zeros((len(docs), EMBEDDER.dim), dtype="float32")
        if not docs:
            return out
        order = sorted(range(len(docs)), key=lambda i: len(docs[i]))
        for start in range(0, len(order), BATCH):
            chunk = order[start:start + BATCH]
            vecs = EMBEDDER.encode([docs[i] for i in chunk], is_query=False)
            out[chunk] = np.asarray(vecs, dtype="float32")
        return out

    def build(self, entries, doc_fn):
        """构建索引。doc_fn(entry) -> 用于编码的文本。

        命中缓存时跳过编码（启动 <50ms），未命中则批量编码后落盘。
        """
        self.entries = list(entries)
        self._docs = [(e.get("id") or str(i), doc_fn(e)) for i, e in enumerate(self.entries)]
        self.ids = [d[0] for d in self._docs]

        cache_file = self._cache_file()
        if os.path.isfile(cache_file):
            try:
                import numpy as np
                with np.load(cache_file) as data:
                    matrix, ids = data["vectors"], [str(x) for x in data["ids"]]
                if len(ids) == len(self.entries) and ids == self.ids:
                    self.matrix = matrix
                    self.dim = int(matrix.shape[1])
                    self.from_cache = True
                    self.built_at = time.strftime("%H:%M:%S")
                    return self
            except Exception:
                pass                      # 缓存损坏则重建，不向上抛

        import numpy as np
        self.matrix = self._encode_batched([d[1] for d in self._docs])
        self.dim = int(self.matrix.shape[1])
        self.from_cache = False
        self.built_at = time.strftime("%H:%M:%S")

        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            np.savez_compressed(cache_file, vectors=self.matrix,
                                ids=np.array(self.ids, dtype="U64"))
            # 清掉同一索引的旧缓存，避免目录里堆历史版本
            for fn in os.listdir(CACHE_DIR):
                if fn.startswith(self.name + "-") and fn != os.path.basename(cache_file):
                    try:
                        os.remove(os.path.join(CACHE_DIR, fn))
                    except OSError:
                        pass
        except Exception:
            pass                          # 缓存写不进去不影响检索
        return self

    # ---------------------------------------------------------------- 检索
    def scores(self, query):
        """返回与 self.entries 对齐的相似度数组（float32，余弦相似度 ∈ [-1,1]）。"""
        import numpy as np
        if self.matrix is None or not len(self.entries):
            return np.zeros(0, dtype="float32")
        q = EMBEDDER.encode(query, is_query=True)          # query 侧加 BGE 指令前缀
        q = np.asarray(q, dtype="float32").reshape(-1)
        if q.shape[0] != self.matrix.shape[1]:
            return np.zeros(len(self.entries), dtype="float32")
        return self.matrix @ q

    def ranked(self, query, top_k=None, indices=None):
        """返回 [(原始下标, 相似度)]，按相似度降序。indices 可限定候选集。"""
        all_scores = self.scores(query)
        if not len(all_scores):
            return []
        if indices is not None:
            pool = [(i, float(all_scores[i])) for i in indices]
        else:
            pool = list(enumerate(all_scores.tolist()))
        pool.sort(key=lambda x: x[1], reverse=True)
        return pool[:top_k] if top_k else pool

    def info(self):
        return {
            "name": self.name,
            "entries": len(self.entries),
            "dim": self.dim,
            "from_cache": self.from_cache,
            "built_at": self.built_at,
            "cache": "hit" if self.from_cache else "built",
        }


# --------------------------------------------------------------- 单例与预热
_INDEXES = {}
_LOAD_LOCK = threading.Lock()


def _doc_statute(entry):
    """法条编码文本：法律名 + 条号 + 正文。带上法律名有助于区分
    《劳动合同法》第 38 条与《劳动法》第 32 条这类近似条款。"""
    return "%s%s %s" % (entry.get("law_short") or entry.get("law", ""),
                        entry.get("article", ""), entry.get("text", ""))


def _doc_case(case):
    """注意 focus / keywords 是列表，不能直接做字符串拼接。"""
    parts = [case.get("title", ""), case.get("summary", ""), case.get("holding", "")]
    parts += [str(x) for x in (case.get("focus") or [])]
    parts += [str(x) for x in (case.get("keywords") or [])]
    return " ".join(p for p in parts if p)


def get_index(name, entries):
    """取（必要时构建）指定语料的索引。进程内单例，重复调用零开销。"""
    with _LOAD_LOCK:
        idx = _INDEXES.get(name)
        if idx is not None and len(idx.entries) == len(entries):
            return idx
    doc_fn = _doc_statute if name == "statutes" else _doc_case
    idx = VectorIndex(name).build(entries, doc_fn)
    with _LOAD_LOCK:
        _INDEXES[name] = idx
    return idx


def prewarm():
    """预热全部索引。放在服务启动时调用，避免首个用户请求承担建库耗时。"""
    from . import rag
    t0 = time.time()
    idx = rag.statute_index()
    out = {"statutes": idx.info(), "ms": int((time.time() - t0) * 1000),
           "embedder": EMBEDDER.name}
    return out


def all_info():
    return {k: v.info() for k, v in _INDEXES.items()}

