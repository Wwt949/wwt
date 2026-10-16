"""RAG 检索增强生成 —— 混合检索（稠密向量召回 + 词面召回，RRF 融合）。

对应 PPT 第 10 页策略②「向量库检索」与第 13 页「混合检索 + 精排」：

    查询 ─┬─ 稠密通道：BGE-small-zh 向量 → 余弦相似度 Top-N ─┐
          └─ 词面通道：关键词命中 + 字符二元组重合 Top-N ─────┤
                                                            ├─ RRF 融合 → Top-K
                        案件类型（category）元数据先验 ────────┘

两条通道互补：向量通道擅长同义改写（"没签合同" ≈ "未订立书面劳动合同"），
词面通道擅长法条号、专有名词、否定表达这类向量容易糊掉的精确信号。
用 RRF（Reciprocal Rank Fusion）按**排名**而非分数融合，天然规避了两路分数量纲
不可比的问题，k 取标准的 60。

对外接口与 Phase 0 完全一致，tools.py / generator.py 无需改动。
"""
import json
import math
import os

from . import config, vector_index
from .embed import EMBEDDER
from .textutil import bigrams, keyword_present

_KB_CACHE = {}

# 稠密通道准入门槛。BGE 余弦相似度实测：语义等价 0.5~0.7，无关 ≈0.2，
# 取 0.30 作地板可挡掉纯噪声，又不会误杀弱相关的正确条款。
DENSE_FLOOR = float(os.environ.get("LEGALASSIST_DENSE_FLOOR", "0.30"))


def _load(name):
    if name not in _KB_CACHE:
        with open(os.path.join(config.DATA_DIR, name), "r", encoding="utf-8") as f:
            _KB_CACHE[name] = json.load(f)
    return _KB_CACHE[name]


# ------------------------------------------------------------------ 索引单例
def statute_index():
    kb = _load("law_kb.json")
    return vector_index.get_index("statutes", kb["entries"])


def case_index():
    data = _load("cases.json")
    return vector_index.get_index("cases", data["cases"])


# ------------------------------------------------------------------ 词面通道
class _LexicalIndex:
    """IDF 加权的字符二元组索引（轻量 BM25 思路）。

    为什么不能直接数公共二元组的个数：法条语料里「劳动」「合同」「用人单位」
    这类二元组几乎条条都有，数个数只会让所有条文分数挤成一团——实测一次查询有
    30 条并列同一分数，排序退化成"按条号先后"，反而盖过了向量通道的正确结果。
    按 IDF 加权后，稀有二元组（「二倍」「竞业」「不可抗力」）才有区分度，
    常见二元组自动接近零权重。

    条目侧二元组集合在建索引时算一次，避免每次查询重复切分 1000+ 条正文。
    """

    def __init__(self, docs):
        self.sets = [bigrams(d) for d in docs]
        df = {}
        for s in self.sets:
            for g in s:
                df[g] = df.get(g, 0) + 1
        self.df = df
        self.n = max(len(docs), 1)

    def idf(self, gram):
        # 平滑版 IDF：df 越大权重越低，出现在全部文档里的二元组权重趋近 log(2)≈0.69 以下
        return math.log(1.0 + self.n / (1.0 + self.df.get(gram, 0)))

    def overlap(self, query, idx):
        """返回 (加权重合分, 命中的高权重二元组)。"""
        q = bigrams(query)
        if not q:
            return 0.0, []
        shared = q & self.sets[idx]
        if not shared:
            return 0.0, []
        scored = sorted(((self.idf(g), g) for g in shared), reverse=True)
        return sum(w for w, _ in scored), [g for _, g in scored]


_LEX_CACHE = {}


def _case_doc(case):
    """案例检索文本。注意 focus / keywords 是列表，拼接前必须展平。"""
    parts = [case.get("title", ""), case.get("summary", ""), case.get("holding", "")]
    parts += [str(x) for x in (case.get("focus") or [])]
    parts += [str(x) for x in (case.get("keywords") or [])]
    return " ".join(p for p in parts if p)


def _lexical_index(name, docs):
    if name not in _LEX_CACHE:
        _LEX_CACHE[name] = _LexicalIndex(docs)
    return _LEX_CACHE[name]


def _lexical_score(query, entry, lex_idx, idx):
    """词面相关度 = IDF 加权二元组重合 + 人工关键词命中加分。

    案件类型不再进分数，改由 search_statutes 的同类型/跨类型分段检索处理——
    之前把类型加成算进分数里，反而制造了大量同分并列。

    返回三元组 (分数, 人工词表命中, 字面重合片段)。后两者分开返回：词表命中
    是真正可读的关键词；二元组片段只是字面重合（「面劳」来自"书面劳动合同"），
    展示成"命中关键词"会像乱码，因此单独放在 match_terms 里备用。
    """
    score, terms = lex_idx.overlap(query, idx)
    low = query.lower()
    hits = []
    for kw in entry.get("keywords", []):
        if keyword_present(low, kw):          # 否定感知：排除"没签合同"式误命中
            score += 2.0 + min(len(kw), 6) * 0.2
            hits.append(kw)
    return score, hits[:5], terms[:3]


def _overlap_terms(query, entry, lex_idx, idx, limit=5):
    """稠密命中但没有关键词命中的条目，用 IDF 最高的公共二元组当解释性依据。

    这些二元组是字面真实重合的，不是编造的，因此可以放心展示给用户。
    """
    _score, terms = lex_idx.overlap(query, idx)
    return terms[:limit] or sorted(bigrams(query) & bigrams(entry.get("text", "")),
                                   key=len, reverse=True)[:limit]


# ------------------------------------------------------------------ 融合检索
def _fuse(query, idx, lex_idx, entries, candidate_idx, top_k, min_score):
    """对候选集跑双通道召回 + RRF 融合，返回 [(下标, 融合分, 稠密分, 词面分, 命中词)]。"""
    if not candidate_idx:
        return []

    recall = max(top_k * config.RECALL_MULTIPLIER, top_k)
    dense_hits = dict(idx.ranked(query, top_k=recall, indices=candidate_idx))

    lexical = []
    for i in candidate_idx:
        s, hits, terms = _lexical_score(query, entries[i], lex_idx, i)
        if s >= min_score:
            lexical.append((s, i, hits, terms))
    lexical.sort(key=lambda x: -x[0])
    lexical = lexical[:recall]
    lexical_map = {i: (s, hits, terms) for s, i, hits, terms in lexical}

    fused = {}
    for rank, i in enumerate(sorted(dense_hits, key=lambda k: -dense_hits[k])):
        fused[i] = fused.get(i, 0.0) + config.RRF_WEIGHT_DENSE / (config.RRF_K + rank + 1)
    for rank, (_s, i, _h, _t) in enumerate(lexical):
        fused[i] = fused.get(i, 0.0) + config.RRF_WEIGHT_LEXICAL / (config.RRF_K + rank + 1)

    out = []
    for i, rrf in fused.items():
        dense_sim = float(dense_hits.get(i, 0.0))
        lex_score, hits, terms = lexical_map.get(i, (0.0, [], []))
        # 准入门槛：稠密得分够高，或词面确实命中。两者皆无 = 噪声，丢弃。
        if dense_sim < DENSE_FLOOR and lex_score < min_score:
            continue
        if not terms and dense_sim >= DENSE_FLOOR:
            terms = _overlap_terms(query, entries[i], lex_idx, i)
        out.append((i, rrf, dense_sim, lex_score, hits, terms))

    out.sort(key=lambda x: -x[1])
    return out[:top_k]


def _format_statute(idx, score_row, max_rrf):
    i, rrf, dense_sim, lex_score, hits, terms = score_row
    entry = idx.entries[i]
    return {
        "id": entry["id"],
        "law": entry["law"],
        "article": entry["article"],
        "title": entry["title"],
        # ---- Phase 0 起就有的字段，语义与取值口径保持不变 ----
        "text": entry["text"],
        "source": entry["source"],
        "category": entry["category"],
        "matched_keywords": hits,
        "match_terms": terms,                     # 字面重合片段，仅作可解释性参考
        "relevance": round(min(0.99, rrf / max_rrf), 2) if max_rrf else 0.0,
        "score": round(rrf * 1000, 3),            # 融合分（按名次融合，仅用于排序比较）
        # ---- Phase 1 新增：可解释性字段 ----
        "dense_score": round(dense_sim, 4),       # BGE 余弦相似度，绝对值可直接判读
        "lexical_score": round(lex_score, 3),     # 词面通道原始分
        "retrieval": ("dense+lexical" if dense_sim >= DENSE_FLOOR and lex_score >= 1.0
                      else ("dense" if dense_sim >= DENSE_FLOOR else "lexical")),
        # ---- 时效元数据（Phase 1 新增，供「现行有效」校验与风险提示使用）----
        "status": entry.get("status", ""),
        "effective_date": entry.get("effective_date", ""),
        "section_path": entry.get("section_path", ""),
    }


def search_statutes(query, category="other", top_k=4, min_score=1.0):
    """检索 Top-K 法条：先在同案件类型内召回，不足时再跨类型兜底。"""
    idx = statute_index()
    entries = idx.entries
    lex_idx = _lexical_index("statutes", [e.get("title", "") + e.get("text", "") for e in entries])

    if category == "other" or not config.HYBRID_RETRIEVAL:
        pool = list(range(len(entries)))
        rows = _fuse(query, idx, lex_idx, entries, pool, top_k, min_score)
    else:
        in_cat = [i for i, e in enumerate(entries) if e.get("category") == category]
        out_cat = [i for i, e in enumerate(entries) if e.get("category") != category]
        rows = _fuse(query, idx, lex_idx, entries, in_cat, top_k, min_score)
        if len(rows) < top_k:
            rows += _fuse(query, idx, lex_idx, entries, out_cat, top_k - len(rows), min_score)

    max_rrf = rows[0][1] if rows else 1.0
    return [_format_statute(idx, r, max_rrf) for r in rows]


def search_cases(summary, focus_keywords=None, category="other", top_k=2, min_score=1.0):
    """检索同类裁判文书。案例库只有 8 条，直接走词面通道更稳（向量在极小库上易过拟合）。"""
    data = _load("cases.json")
    query = summary + " " + " ".join(focus_keywords or [])
    lex_idx = _lexical_index("cases", [_case_doc(c) for c in data["cases"]])
    ranked = []
    for i, case in enumerate(data["cases"]):
        score, hits, terms = _lexical_score(query, case, lex_idx, i)
        if score >= min_score:
            ranked.append((score, hits or terms, case))
    ranked.sort(key=lambda x: x[0], reverse=True)

    # 词面没召回时退回向量通道（案例文本长、口语化，向量有一定泛化能力）
    if not ranked:
        idx = case_index()
        for i, sim in idx.ranked(query, top_k=top_k):
            if sim >= DENSE_FLOOR:
                case = idx.entries[i]
                ranked.append((sim * 10, _overlap_terms(query, case, lex_idx, i), case))

    max_score = ranked[0][0] if ranked else 1.0
    return [{
        "id": c["id"],
        "case_no": c["case_no"],
        "court": c["court"],
        "title": c["title"],
        "summary": c["summary"],
        "focus": c["focus"],
        "holding": c["holding"],
        "result": c["result"],
        "matched_keywords": m,
        "relevance": round(min(0.99, s / max_score), 2),
    } for s, m, c in ranked[:top_k]]


def kb_stats():
    kb = _load("law_kb.json")
    cases = _load("cases.json")
    by_cat = {}
    for e in kb["entries"]:
        by_cat[e["category"]] = by_cat.get(e["category"], 0) + 1
    return {
        "statutes": len(kb["entries"]),
        "cases": len(cases["cases"]),
        "by_category": by_cat,
        "version": kb["version"],
        "retrieval": "hybrid(dense+lexical, RRF k=%d)" % config.RRF_K,
        "embedder": EMBEDDER.name,
        "semantic": EMBEDDER.is_semantic,
    }

