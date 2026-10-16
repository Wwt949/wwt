"""检索质量评测：用一批「口语化提问 → 应命中的法条」标注对，量化召回效果。

对比三档：
  lexical  仅词面通道（等价 Phase 0）
  dense    仅稠密通道（BGE-small-zh）
  hybrid   双通道 RRF 融合（Phase 1 实际采用）

指标：Hit@1 / Hit@3 / MRR。人工标注较小（30 题），结论仅供参考，
但足以看出向量通道相对纯关键词的增量。

用法:  python tools/eval_retrieval.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from engine import config, rag, vector_index  # noqa: E402
from engine.embed import EMBEDDER            # noqa: E402

# (口语化提问, 案件类型, 期望命中的法条 id 集合)   —— id 命中任意一个即算对
# 标注说明：期望集合按「该提问下站得住脚的条款」收，不唯一。某些提问确实有多个
# 同样正确的落点（如"一物二卖"既可答合同编通则 577，也可答买卖分则 597），
# 命中任一即算对；只收真正答非所问的情况算错。
CASES = [
    ("公司一直不跟我签书面劳动合同，能要双倍工资吗", "labor", ["劳动合同法-82", "劳动合同法-10"]),
    ("老板拖欠工资好几个月了怎么办", "labor",
     ["劳动法-50", "劳动合同法-30", "劳动合同法-85", "劳动法-91", "劳动争议调解仲裁法-9"]),
    ("公司没给我缴社保，我可以直接走人吗", "labor", ["劳动合同法-38"]),
    ("辞职要提前多久通知公司", "labor", ["劳动合同法-37", "劳动法-31"]),
    ("公司用试用期当借口不发全额工资", "labor", ["劳动合同法-20", "劳动法-21"]),
    ("单位要辞退我，需要给我经济补偿吗", "labor", ["劳动合同法-46", "劳动合同法-47"]),
    ("无缘无故被开除了，能拿赔偿金吗", "labor", ["劳动合同法-48", "劳动合同法-87"]),
    ("加班没有加班费怎么算", "labor", ["劳动法-44", "劳动合同法-31"]),
    ("工伤了单位不管，该怎么赔", "labor",
     ["劳动法-73", "工伤保险条例-14", "工伤保险条例-17", "工伤保险条例-62"]),
    ("劳动者可以单方面解除劳动合同的情形", "labor", ["劳动合同法-38", "劳动法-32"]),
    ("劳动合同到期公司不续签要给钱吗", "labor", ["劳动合同法-46", "劳动合同法-47"]),
    ("公司天天加班超过法定工时违法吗", "labor", ["劳动法-36", "劳动法-41"]),
    ("申请劳动仲裁要花钱吗，多久内必须申请", "labor",
     ["劳动争议调解仲裁法-27", "劳动争议调解仲裁法-53", "劳动争议调解仲裁法-2"]),
    ("跟公司发生劳动争议，是先去仲裁还是直接起诉", "labor",
     ["劳动争议调解仲裁法-5", "劳动争议调解仲裁法-2"]),

    ("想离婚，对方不同意，怎么起诉", "marriage", ["民法典-1079"]),
    ("老公出轨了，我能要求离婚损害赔偿吗", "marriage", ["民法典-1091"]),
    ("夫妻共同财产离婚的时候怎么分", "marriage", ["民法典-1087", "民法典-1062"]),
    ("对方家暴，我能申请人身安全保护令吗", "marriage", ["民法典-1042", "民法典-1079"]),
    ("离婚后孩子归谁抚养", "marriage", ["民法典-1084"]),
    ("一方欠的赌债另一方要一起还吗", "marriage", ["民法典-1064"]),

    ("对方收了定金不发货，我能要双倍返还吗", "contract", ["民法典-587", "民法典-586"]),
    ("签了合同对方一直不履行，我想解除合同", "contract", ["民法典-563", "民法典-577"]),
    ("合同里写的违约金太高可以要求降低吗", "contract", ["民法典-585"]),
    ("卖家把同一批货卖给了两个人，我怎么办", "contract",
     ["民法典-597", "民法典-577", "民法典-580"]),     # 597 = 无权处分致所有权不能转移，一物二卖的直接依据
    ("买东西交了钱对方跑路了", "contract", ["民法典-577", "民法典-566"]),
    ("被中介骗了签的合同有效吗", "contract", ["民法典-148", "民法典-152", "民法典-962"]),
    ("合同是被人胁迫签的，能撤销吗", "contract", ["民法典-150"]),
    ("口头约定算不算合同", "contract", ["民法典-469", "民法典-135"]),
    ("借钱给别人对方不还，多久内必须起诉", "contract", ["民法典-188", "民法典-675"]),
    ("对方根本违约，我能直接解除合同并索赔吗", "contract", ["民法典-563", "民法典-577"]),

    ("借条没写利息，到期能要利息吗", "loan", ["民间借贷司法解释-24", "民法典-680"]),
    ("民间借贷利息最多能约定多少", "loan", ["民间借贷司法解释-25"]),

    # ---- 以下刻意使用规范法律术语：考察词面通道的强项（精确术语 / 条号 / 法条名）
    ("经济补偿金按什么标准计算", "labor", ["劳动合同法-47"]),
    ("什么情况下用人单位应当向劳动者支付经济补偿", "labor", ["劳动合同法-46"]),
    ("试用期最长可以约定多久", "labor", ["劳动合同法-19", "劳动法-21"]),
    ("竞业限制的期限最长是几年", "labor", ["劳动合同法-24"]),
    ("劳动者违反竞业限制要付违约金吗", "labor", ["劳动合同法-23"]),
    ("违约金过分高于造成的损失可以请求调整吗", "contract", ["民法典-585"]),
    ("什么情形构成不可抗力", "contract", ["民法典-590", "民法典-180"]),
    ("不安抗辩权应当如何行使", "contract", ["民法典-527"]),
    ("债务人转让债务需要债权人同意吗", "contract", ["民法典-551"]),
    ("离婚冷静期是多少天", "marriage", ["民法典-1077"]),
    ("哪些债务属于夫妻共同债务", "marriage", ["民法典-1064"]),
    ("诉讼时效期间是多长时间", "contract", ["民法典-188"]),
]


def hit_rank(results, expected):
    if not expected:
        return None                     # 无期望条款，不计分
    for rank, r in enumerate(results, 1):
        if r["id"] in expected:
            return rank
    return 0


def evaluate(mode):
    """mode: lexical | dense | hybrid —— 通过临时改写检索路径实现三档对比。"""
    import numpy as np

    idx = rag.statute_index()
    entries = idx.entries
    id2i = {e["id"]: i for i, e in enumerate(entries)}

    hits = {1: 0, 3: 0}
    mrr = 0.0
    total = 0
    details = []

    for query, category, expected in CASES:
        if not expected:
            continue
        total += 1

        if mode == "lexical":
            lex_idx = rag._lexical_index(
                "statutes", [e.get("title", "") + e.get("text", "") for e in entries])
            pool = [i for i, e in enumerate(entries)
                    if category == "other" or e["category"] == category]
            cands = [(i, s) for i in pool
                     for s, _h, _t in [rag._lexical_score(query, entries[i], lex_idx, i)]
                     if s >= 1.0]
            cands.sort(key=lambda x: -x[1])
            got = [entries[i]["id"] for i, _ in cands[:4]]

        elif mode == "dense":
            pool = [i for i, e in enumerate(entries)
                    if category == "other" or e["category"] == category]
            ranked = idx.ranked(query, top_k=4, indices=pool)
            got = [entries[i]["id"] for i, s in ranked if s >= rag.DENSE_FLOOR]

        else:  # hybrid —— 走真实生产路径
            got = [r["id"] for r in rag.search_statutes(query, category=category, top_k=4)]

        rank = next((n for n, gid in enumerate(got, 1) if gid in expected), 0)
        if rank:
            mrr += 1.0 / rank
            if rank == 1:
                hits[1] += 1
            if rank <= 3:
                hits[3] += 1
        details.append((query, category, expected, got, rank))

    return {
        "mode": mode, "total": total,
        "hit1": hits[1] / total, "hit3": hits[3] / total, "mrr": mrr / total,
        "details": details,
    }


def sweep():
    """扫描 RRF 词面通道权重，选出让 Hit@1 / MRR 最好的取值。

    经典 RRF 等权（1.0）在本场景不是最优——两路质量不对等时必须实测再定，
    这也是 config.RRF_WEIGHT_LEXICAL 默认值 0.35 的来源。
    """
    print("RRF 词面通道权重扫描（稠密通道固定 1.0）")
    print("%-8s %10s %10s %10s" % ("w_lex", "Hit@1", "Hit@3", "MRR"))
    print("-" * 42)
    rows = []
    for w in (0.0, 0.15, 0.25, 0.35, 0.5, 0.7, 1.0):
        config.RRF_WEIGHT_LEXICAL = w
        r = evaluate("hybrid")
        rows.append((w, r))
        star = ""
        if r["hit1"] == max(x[1]["hit1"] for x in rows):
            star = "  ← 当前最优"
        print("%-8.2f %9.1f%% %9.1f%% %10.3f%s" % (w, r["hit1"] * 100, r["hit3"] * 100,
                                                   r["mrr"], star))
    best = max(rows, key=lambda x: (x[1]["hit1"], x[1]["mrr"]))
    print("\n最佳词面权重: %.2f  (Hit@1 %.1f%%, MRR %.3f)"
          % (best[0], best[1]["hit1"] * 100, best[1]["mrr"]))
    config.RRF_WEIGHT_LEXICAL = best[0]
    return best[1]


def main():
    if "--sweep" in sys.argv:
        EMBEDDER  # noqa: B018
        rag.statute_index()
        sweep()
        return

    print("嵌入后端: %s  维度: %s  语义能力: %s"
          % (EMBEDDER.name, EMBEDDER.dim, EMBEDDER.is_semantic))
    if not EMBEDDER.is_semantic:
        print("⚠️  当前是 hash 兜底后端，dense 通道无真实语义能力，评测结果不代表 Phase 1 水平")
    t0 = __import__("time").time()
    rag.statute_index()
    print("法条库: %d 条  建库耗时: %dms\n"
          % (len(rag.statute_index().entries), (__import__("time").time() - t0) * 1000))

    report = {}
    for mode in ("lexical", "dense", "hybrid"):
        report[mode] = evaluate(mode)

    print("%-10s %10s %10s %10s" % ("通道", "Hit@1", "Hit@3", "MRR"))
    print("-" * 44)
    for mode in ("lexical", "dense", "hybrid"):
        r = report[mode]
        print("%-10s %9.1f%% %9.1f%% %10.3f" % (mode, r["hit1"] * 100, r["hit3"] * 100, r["mrr"]))

    base, hyb = report["lexical"], report["hybrid"]
    print("\n融合 vs 纯词面:  Hit@1 %+.1fpp   Hit@3 %+.1fpp   MRR %+.3f"
          % ((hyb["hit1"] - base["hit1"]) * 100, (hyb["hit3"] - base["hit3"]) * 100,
             hyb["mrr"] - base["mrr"]))

    print("\n逐题明细（hybrid 未命中或被 dense 翻盘的题目）:")
    misses = 0
    for (q, cat, exp, got_l, r_l), (_, _, _, got_h, r_h) in zip(base["details"], hyb["details"]):
        if r_h == 0 or r_h > 3 or (r_l == 0 and r_h > 0) or (r_l > 0 and r_h == 0):
            misses += 1
            tag = "❌未命中" if r_h == 0 else ("🆕dense救回" if r_l == 0 else
                                          ("⬆️" if r_h < r_l else "⬇️"))
            print("  %-6s 排名 %s→%s  %s" % (tag, r_l or "-", r_h or "-", q))
            print("         期望 %s" % exp)
            print("         实得 %s" % got_h[:4])
    if not misses:
        print("  （无）")


if __name__ == "__main__":
    main()

