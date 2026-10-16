"""回答生成 + Prompt 工程 + 多轮记忆管理（PPT 第 10 页四大策略）。

① 系统角色设定   -> SYSTEM_ROLE
② RAG 上下文动态注入 -> build_prompt() 把检索结果按相关度排序拼入
③ 输出格式结构化约束 -> 强制三段式：法律依据 -> 证据清单 -> 维权路径
④ 多轮记忆管理   -> compress_history() 超 N 轮压缩历史
"""
from . import config, llm

SYSTEM_ROLE = (
    "你是一名从业十五年的资深法律顾问，专业领域为劳动纠纷、婚姻家事、合同纠纷与民间借贷。"
    "回答要求：严谨、克制、可执行；只依据现行有效法律法规与检索到的条文作答；"
    "不得承诺案件结果；不得编造法条或案号；证据不足时明确提示不利后果并引导线下委托律师。"
)

REMEDY_PATH = {
    "labor": [
        "与用人单位书面协商，全程留存沟通记录（建议使用微信/邮件等可留痕方式）",
        "向用人单位所在地劳动保障监察大队投诉举报（热线 12333），或向劳动争议调解组织申请调解",
        "向劳动合同履行地或用人单位所在地劳动人事争议仲裁委员会申请劳动仲裁（仲裁时效 1 年，务必优先处理）",
        "对仲裁裁决不服的，自收到裁决书之日起 15 日内向人民法院起诉",
    ],
    "marriage": [
        "协议离婚：双方签订书面离婚协议 -> 共同到婚姻登记机关申请 -> 30 日冷静期届满后 30 日内共同申领离婚证",
        "诉讼离婚：向被告住所地（或经常居住地）人民法院提起诉讼，法院应当先行调解",
        "围绕感情破裂、财产线索、子女抚养三方面组织证据",
        "涉及家暴的，可同步申请人身安全保护令，并可主张离婚损害赔偿",
    ],
    "contract": [
        "书面催告对方在合理期限内履行，并保留送达凭证（EMS 注明文件名称）",
        "核对合同中的争议解决条款：约定仲裁的走仲裁，否则向被告住所地或合同履行地法院起诉",
        "同步申请财产保全，防止对方转移资产（实务中影响回款的关键动作）",
        "诉讼时效 3 年，自知道权利受损之日起算，注意留存催告导致时效中断的证据",
    ],
    "loan": [
        "书面催收并留存送达凭证（催收行为可导致诉讼时效中断并重新计算 3 年）",
        "债权债务关系明确、无其他争议的，可向法院申请支付令，成本低、周期短",
        "向被告住所地或合同履行地人民法院提起诉讼，并申请财产保全",
        "主张利息时注意：超过合同成立时一年期 LPR 四倍的部分不受法律保护",
    ],
    "other": [
        "先固定现有证据材料，形成书面事实经过",
        "通过人民调解委员会或行业调解组织先行调解",
        "根据法律关系性质确定管辖法院，注意 3 年诉讼时效",
        "案情复杂或标的较大的，建议委托专业律师介入",
    ],
}


def build_prompt(history_summary, statutes, cases, user_text, intent):
    """按 PPT 策略②：把检索上下文按相关度排序后动态注入 Prompt。"""
    ctx = []
    for i, s in enumerate(statutes, 1):
        ctx.append("[法条%d|相关度%.2f] %s%s《%s》\n%s" % (
            i, s["relevance"], s["law"], s["article"], s["title"], s["text"]))
    for i, c in enumerate(cases, 1):
        ctx.append("[案例%d|相关度%.2f] %s %s\n裁判要旨：%s\n裁判结果：%s" % (
            i, c["relevance"], c["case_no"], c["title"], c["holding"], c["result"]))

    prompt = []
    if history_summary:
        prompt.append("【会话历史摘要】\n" + history_summary)
    prompt.append("【检索到的法条与案例（按相关度降序）】\n" + ("\n\n".join(ctx) if ctx else "（无匹配结果）"))
    prompt.append("【本轮用户问题】\n" + user_text)
    prompt.append(
        "【输出格式约束】严格按三段式作答，并在末尾附风险提示：\n"
        "一、法律依据（引用具体法条，标注法律名称与条号）\n"
        "二、证据清单（区分「你已具备」与「建议补充」）\n"
        "三、维权路径（按时间顺序给出可执行步骤）\n"
        "⚠️ 风险提示（诉讼时效、举证难度、结果不确定性）\n"
        "已知案件类型：%s；用户诉求类型：%s。" % (intent["category_label"], intent["sub_intent_label"])
    )
    return "\n\n".join(prompt)


def _fmt_amount(entities):
    if not entities.get("amount"):
        return ""
    return "、".join("约 %g 元" % a["yuan"] for a in entities["amount"][:3])


def render_answer(intent, user_text, statute_result, case_result, risk_result, session):
    """本地规则引擎渲染三段式回答（mock 模式下即最终输出）。"""
    lines = []
    e = intent["entities"]

    # ---- 开场分析
    clues = []
    if e.get("amount"):
        clues.append("涉案金额 " + _fmt_amount(e))
    if e.get("duration"):
        clues.append("时间跨度 " + "、".join(e["duration"][:3]))
    if e.get("parties"):
        clues.append("相对方 " + "、".join(e["parties"][:3]))

    lines.append("【初步研判】识别为 **%s**（置信度 %.0f%%），诉求倾向：%s。" % (
        intent["category_label"], intent["confidence"] * 100, intent["sub_intent_label"]))
    if clues:
        lines.append("已提取要素：" + "；".join(clues) + "。")
    lines.append("")

    # ---- 一、法律依据
    lines.append("**一、法律依据**")
    if statute_result["hit_count"]:
        for i, s in enumerate(statute_result["results"], 1):
            snippet = s["text"][:110] + ("…" if len(s["text"]) > 110 else "")
            lines.append("%d. %s%s《%s》—— %s" % (i, s["law"], s["article"], s["title"], snippet))
    else:
        lines.append("未检索到高度匹配的具体条款，建议补充案情细节（争议焦点、时间、金额）。")
    lines.append("")

    # ---- 二、证据清单
    lines.append("**二、证据清单**")
    found = risk_result["evidence"]["found"]
    missing = risk_result["evidence"]["missing"]
    claims = risk_result.get("claims", [])
    if claims:
        lines.append("· 你主张的事实（需证据证明）：%s" % "；".join(claims))
    lines.append("· 你已具备的凭证：%s" % ("、".join(found) if found else "暂未识别到，请补充"))
    lines.append("· 建议补充固定：%s" % ("、".join(missing[:5]) if missing else "暂无"))
    lines.append("· 凭证覆盖率：%.0f%%（%d/%d）" % (
        risk_result["evidence"]["coverage"] * 100,
        len(found), len(found) + len(missing)))
    lines.append("")

    # ---- 三、维权路径
    lines.append("**三、维权路径**")
    for i, step in enumerate(REMEDY_PATH.get(intent["category"], REMEDY_PATH["other"]), 1):
        lines.append("%d. %s" % (i, step))
    lines.append("")

    # ---- 风险提示
    lines.append("**⚠️ 风险提示**")
    lines.append("· 风险评估：**%s**；胜诉概率区间（模型估算）%.0f%% ~ %.0f%%" % (
        risk_result["risk_level"],
        risk_result["win_probability"]["low"] * 100,
        risk_result["win_probability"]["high"] * 100))
    lines.append("· " + risk_result["limitation_advice"])
    for r in risk_result["risks"]:
        lines.append("· [%s风险] %s —— %s" % (r["level"], r["point"], r["advice"]))
    lines.append("")

    # ---- 案例参考
    if case_result["hit_count"]:
        lines.append("**四、类案参考**")
        for c in case_result["results"]:
            lines.append("· %s（%s）：%s → **%s**" % (c["case_no"], c["court"], c["holding"][:80] + "…", c["result"]))
        lines.append("· ⚠️ 以上案例为演示用虚构样例，实际引用请核实裁判文书原文。")
        lines.append("")

    lines.append("---")
    lines.append("_" + config.DISCLAIMER + "_")

    text = "\n".join(lines)

    # 多轮记忆：把关键事实沉淀到会话摘要，供 B 端分析使用
    facts = session.setdefault("key_facts", [])
    for k, v in [("案件类型", intent["category_label"]),
                 ("诉求", intent["sub_intent_label"]),
                 ("金额", _fmt_amount(e) or None),
                 ("时长", "、".join(e["duration"][:2]) or None)]:
        if v and ("%s=%s" % (k, v)) not in facts:
            facts.append("%s=%s" % (k, v))
    return text


def generate(session, user_text, intent, statute_result, case_result, risk_result):
    """生成回答：组装 Prompt -> 经 MoMA 路由调用模型 -> 返回文本与调用元信息。"""
    history_summary = session.get("summary", "")
    prompt = build_prompt(history_summary, statute_result["results"],
                          case_result["results"], user_text, intent)
    mock_text = render_answer(intent, user_text, statute_result, case_result, risk_result, session)
    turns = sum(1 for m in session.get("history", []) if m["role"] == "user")
    complexity = (
        1
        + (1 if len(statute_result["results"]) >= 4 else 0)   # 涉及多部法律法规
        + (1 if intent["strong_intent_signals"] else 0)       # 已表达委托/诉讼意向
        + (1 if turns >= 3 else 0)                            # 长会话上下文
    )
    return llm.CLIENT.complete("dialogue", prompt, mock_text, complexity=complexity)


def compress_history(history):
    """策略④：会话摘要 + 关键事实提取，控制上下文窗口长度。"""
    if len(history) <= config.MEMORY_COMPRESS_AFTER_TURNS:
        return None, False
    user_msgs = [m["content"] for m in history if m["role"] == "user"]
    summary = "用户先后提出 %d 个问题，聚焦于：%s" % (
        len(user_msgs), " / ".join(m[:28] for m in user_msgs[-4:]))
    return summary, True

