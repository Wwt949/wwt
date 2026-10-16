"""B 端 · AI 意向客户分析引擎（对应 PPT 第 4 页 B 端 & 第 6 页「AI 意向客户分析流程」）。

输入：完整咨询会话（多轮上下文）
输出：案件类型标签 / 诉求拆解 / 证据现状 / 意向评分 / 跟进建议与沟通要点
"""
from . import llm, tools

# 意向评分因子表（规则可解释，便于律所按自身业务调参）
WEIGHTS = {
    "strong_intent": 22,     # 每命中一个强意向信号
    "strong_intent_cap": 45,
    "turn_bonus_3": 8,       # 会话 >= 3 轮
    "turn_bonus_6": 10,      # 会话 >= 6 轮（追加）
    "clear_category": 12,    # 案件类型明确（非 other）
    "amount_1w": 10,         # 涉案金额 >= 1 万
    "amount_10w": 8,         # 涉案金额 >= 10 万（追加）
    "procedure_ask": 10,     # 主动询问程序 / 时效 / 管辖
    "evidence_ask": 8,       # 主动询问证据
    "urgency": 8,            # 紧迫性表达
    "facts_given": 8,        # 提供了金额 / 时长等具体事实
    "high_risk": 6,          # 风险评估为"高"（用户更倾向寻找专业帮助）
}

GRADE_THRESHOLDS = [(65, "高"), (40, "中"), (0, "低")]


def _collect(session):
    """从会话中汇总分析所需的信号。"""
    history = session.get("history", [])
    user_msgs = [m["content"] for m in history if m["role"] == "user"]
    blob = " ".join(user_msgs)

    intents = session.get("turn_intents", [])
    last = intents[-1] if intents else {}
    # 全会话中出现过的强意向词
    strong = sorted({kw for it in intents for kw in it.get("strong_intent_signals", [])})
    urgency = sorted({kw for it in intents for kw in it.get("urgency_signals", [])})
    sub_intents = [it.get("sub_intent_label") for it in intents if it.get("sub_intent_label")]

    amounts = [a["yuan"] for it in intents for a in it.get("entities", {}).get("amount", [])]
    durations = [d for it in intents for d in it.get("entities", {}).get("duration", [])]
    return {
        "history": history,
        "user_msgs": user_msgs,
        "blob": blob,
        "turns": len(user_msgs),
        "last_intent": last,
        "strong": strong,
        "urgency": urgency,
        "sub_intents": list(dict.fromkeys(sub_intents)),
        "max_amount": max(amounts) if amounts else 0,
        "durations": durations,
    }


def score(sig):
    """意向评分：输出 0-100 分及各因子明细（B 端可解释性要求）。"""
    detail = []
    total = 0

    def add(key, label, value, cap=None):
        nonlocal total
        v = value if cap is None else min(value, cap)
        if v:
            total += v
            detail.append({"factor": label, "key": key, "score": v})

    add("strong_intent", "出现委托/起诉等强意向信号（%s）" % "、".join(sig["strong"][:4]),
        WEIGHTS["strong_intent"] * len(sig["strong"]), WEIGHTS["strong_intent_cap"])
    if sig["turns"] >= 3:
        add("turn_bonus_3", "会话轮次 %d，已完成初步沟通（>=3 轮）" % sig["turns"], WEIGHTS["turn_bonus_3"])
    if sig["turns"] >= 6:
        add("turn_bonus_6", "会话轮次 %d，深度咨询（>=6 轮）" % sig["turns"], WEIGHTS["turn_bonus_6"])
    if sig["last_intent"].get("category") not in (None, "other"):
        add("clear_category", "案件类型明确：%s" % sig["last_intent"].get("category_label", ""), WEIGHTS["clear_category"])
    if sig["max_amount"] >= 10000:
        add("amount_1w", "涉案金额约 %g 元（>=1 万）" % sig["max_amount"], WEIGHTS["amount_1w"])
    if sig["max_amount"] >= 100000:
        add("amount_10w", "涉案金额约 %g 元（>=10 万，高价值线索）" % sig["max_amount"], WEIGHTS["amount_10w"])
    if "程序与时效咨询" in sig["sub_intents"]:
        add("procedure_ask", "主动询问程序 / 时效，行动意愿明确", WEIGHTS["procedure_ask"])
    if "证据咨询" in sig["sub_intents"]:
        add("evidence_ask", "主动询问证据准备", WEIGHTS["evidence_ask"])
    add("urgency", "存在紧迫性表达（%s）" % "、".join(sig["urgency"][:3]), WEIGHTS["urgency"] if sig["urgency"] else 0)
    if sig["max_amount"] or sig["durations"]:
        add("facts_given", "提供了金额 / 时长等具体案情事实", WEIGHTS["facts_given"])

    total = min(100, total)
    grade = next(label for threshold, label in GRADE_THRESHOLDS if total >= threshold)
    return total, grade, detail


def analyze(session):
    """B 端意向客户分析主入口：返回完整 AI 分析报告。"""
    sig = _collect(session)
    if not sig["user_msgs"]:
        return None

    last = sig["last_intent"]
    category = last.get("category", "other")
    risk = tools.tool_assess_risk(last, sig["blob"], " ".join(sig["user_msgs"][:-1]))
    total, grade, detail = score(sig)

    tags = []
    if last.get("category_label"):
        tags.append(last["category_label"])
    tags.extend(last.get("matched_keywords", [])[:4])
    for si in sig["sub_intents"][:2]:
        tags.append(si)

    demands = []
    for it in session.get("turn_intents", []):
        label = it.get("sub_intent_label")
        if label and label not in demands:
            demands.append(label)

    summary = "用户就「%s」进行 %d 轮咨询，诉求为%s。" % (
        last.get("category_label", "法律问题"),
        sig["turns"],
        "、".join(demands) if demands else "了解法律规定",
    )
    if sig["max_amount"]:
        summary += "涉案金额约 %g 元。" % sig["max_amount"]

    # 跟进建议：面向律师的可执行动作
    followups = []
    if grade == "高":
        followups.append("【优先跟进】用户已进入行动准备阶段，建议 2 小时内电话触达")
    elif grade == "中":
        followups.append("【常规跟进】建议 24 小时内微信/电话回访，确认委托意愿")
    else:
        followups.append("【培育】暂为信息了解阶段，纳入内容触达名单，定期推送同类案例")
    if risk["evidence"]["missing"]:
        followups.append("沟通要点：协助补齐关键证据 —— " + "、".join(risk["evidence"]["missing"][:3]))
    followups.append("风险沟通：明确告知胜诉概率区间 %.0f%%~%.0f%%，管理预期后再谈代理" % (
        risk["win_probability"]["low"] * 100, risk["win_probability"]["high"] * 100))
    if risk["risks"]:
        followups.append("抗辩预判：" + risk["risks"][0]["point"])
    if sig["max_amount"]:
        followups.append("报价参考：按标的额约 %d 元与案件复杂度分段报价（演示数据，实际由律所定价）" % int(sig["max_amount"]))
    else:
        followups.append("报价参考：标的额尚未明确，首次沟通需先确认争议金额（当前为演示数据）")

    # 经 DeepSeek-V3 档位生成分析报告文本（mock 模式返回下面这份文本）
    report_lines = [
        "【意向客户分析报告】",
        "线索评级：%s（综合得分 %d/100）" % (grade, total),
        "案件类型：%s   诉求拆解：%s" % (last.get("category_label", "未明确"), "、".join(demands) or "待补充"),
        "案情摘要：%s" % summary,
        "主张事实：" + ("；".join(risk.get("claims", [])) or "尚未形成明确的事实主张"),
        "证据现状：已识别 %d 项，凭证覆盖率 %.0f%%；缺口：%s" % (
            len(risk["evidence"]["found"]), risk["evidence"]["coverage"] * 100,
            "、".join(risk["evidence"]["missing"][:3]) or "无"),
        "风险评估：%s；胜诉概率区间 %.0f%%~%.0f%%" % (
            risk["risk_level"], risk["win_probability"]["low"] * 100, risk["win_probability"]["high"] * 100),
        "评分依据：" + "；".join("%s +%d" % (d["factor"], d["score"]) for d in detail),
        "跟进建议：",
    ] + ["  " + f for f in followups]
    mock_report = "\n".join(report_lines)

    prompt = ("请作为律所案源分析助手，基于以下 C 端咨询会话生成意向客户分析报告，"
              "包含案件标签、诉求拆解、证据现状、风险等级、意向评级与跟进建议。\n\n"
              "会话记录：\n" + "\n".join("- " + m for m in sig["user_msgs"]))
    _, meta = llm.CLIENT.complete("lead_analysis", prompt, mock_report,
                                  complexity=4)

    return {
        "session_id": session["id"],
        "created_at": session.get("created_at"),
        "updated_at": session.get("updated_at"),
        "user_alias": session.get("user_alias", "匿名用户"),
        "grade": grade,
        "score": total,
        "score_detail": detail,
        "tags": tags[:6],
        "demands": demands,
        "summary": summary,
        "turns": sig["turns"],
        "max_amount": sig["max_amount"],
        "risk": risk,
        "followups": followups,
        "report": mock_report,
        "model": meta,
        "follow_status": session.get("follow_status", "待跟进"),
    }

