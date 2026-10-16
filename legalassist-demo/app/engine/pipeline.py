"""端到端编排：C 端智能咨询五步流程（PPT 第 6 页）。

1 用户输入 -> 2 意图识别 -> 3 知识库检索/工具调用 -> 4 生成回答 -> 5 风险提示
每一步都产生一条 trace，前端「工作流时序」面板即渲染这份数据。
"""
from . import generator, llm, nlu, store, tools

STEP = {1: "用户输入", 2: "意图识别", 3: "知识库检索 / 工具调用", 4: "生成回答", 5: "风险提示"}


def handle_chat(session, message):
    trace = []

    # ---------------------------------------------------------- 1. 用户输入
    history = session["history"]
    user_turns = sum(1 for m in history if m["role"] == "user")
    trace.append({
        "step": 1, "name": STEP[1],
        "detail": "接收消费者输入（第 %d 轮），会话累计 %d 字" % (user_turns + 1, len(message)),
        "chars": len(message),
    })

    # ---------------------------------------------------------- 2. 意图识别
    intent = nlu.recognize(message, history)
    intent_text, intent_meta = llm.CLIENT.complete(
        "intent",
        "请识别以下用户问题所属的法律案件类型、用户诉求类型，并抽取金额/时间等实体：\n" + message,
        "[%s / %s / 置信度 %.0f%%]" % (intent["category_label"], intent["sub_intent_label"], intent["confidence"] * 100),
        prompt_len=len(message),
    )
    trace.append({
        "step": 2, "name": STEP[2],
        "detail": "判定案件类型「%s」（置信度 %.0f%%），诉求「%s」；命中关键词：%s" % (
            intent["category_label"], intent["confidence"] * 100, intent["sub_intent_label"],
            "、".join(intent["matched_keywords"][:6]) or "无（沿用历史会话上下文推断）"),
        "model": intent_meta,
        "output": {
            "category": intent["category_label"],
            "sub_intent": intent["sub_intent_label"],
            "confidence": intent["confidence"],
            "entities": intent["entities"],
            "strong_intent_signals": intent["strong_intent_signals"],
        },
    })

    # ------------------------------------------------- 3. 知识库检索 / 工具调用
    statute_result = tools.tool_search_statutes(intent, message)
    trace.append({
        "step": 3, "name": STEP[3] + " · 工具一 法条检索",
        "detail": "命中 %d 条法条：%s" % (
            statute_result["hit_count"],
            "；".join("%s%s(%s)" % (r["law"], r["article"], r["title"]) for r in statute_result["results"][:3]) or "无"),
        "tool_call": statute_result,
    })

    case_result = None
    if tools.should_match_cases(message, user_turns):
        case_result = tools.tool_match_cases(intent, message)
    else:
        case_result = {"tool": "match_cases", "tool_name": "案例匹配", "trigger": "未满足触发条件（用户未询问类案裁判）",
                       "hit_count": 0, "results": [], "input": {}, "focus": []}
    trace.append({
        "step": 3, "name": STEP[3] + " · 工具二 案例匹配",
        "detail": "命中 %d 条类案：%s" % (
            case_result["hit_count"],
            "；".join(c["case_no"] for c in case_result["results"]) or "无"),
        "tool_call": case_result,
    })

    history_text = " ".join(m["content"] for m in history if m["role"] == "user")
    risk_result = tools.tool_assess_risk(intent, message, history_text)
    trace.append({
        "step": 3, "name": STEP[3] + " · 工具三 风险评估",
        "detail": "风险等级「%s」，证据覆盖率 %.0f%%，胜诉概率区间 %.0f%%~%.0f%%" % (
            risk_result["risk_level"], risk_result["evidence"]["coverage"] * 100,
            risk_result["win_probability"]["low"] * 100, risk_result["win_probability"]["high"] * 100),
        "tool_call": risk_result,
    })

    # ---------------------------------------------------------- 4. 生成回答
    answer, gen_meta = generator.generate(session, message, intent, statute_result, case_result, risk_result)
    trace.append({
        "step": 4, "name": STEP[4],
        "detail": "经 MoMA 路由至 %s（%s），组装 Prompt %d 字 -> 输出 %d 字" % (
            gen_meta["model_label"], gen_meta["route_reason"], gen_meta["prompt_chars"], gen_meta["output_chars"]),
        "model": gen_meta,
        "output": {"format": "三段式：法律依据 → 证据清单 → 维权路径"},
    })

    # ---------------------------------------------------------- 5. 风险提示
    trace.append({
        "step": 5, "name": STEP[5],
        "detail": "已附加免责声明；时效提示：%s" % risk_result["limitation_advice"][:40] + "…",
        "output": {
            "risk_level": risk_result["risk_level"],
            "risks": risk_result["risks"],
            "limitation": risk_result["limitation_advice"],
            "disclaimer": True,
        },
    })

    # ------------------------------------------------------ 写入会话（记忆管理）
    history.append({"role": "user", "content": message, "ts": store._now()})
    history.append({"role": "assistant", "content": answer, "ts": store._now()})
    session["turn_intents"].append(intent)
    session["turn_traces"].append(trace)
    session["lead_cache"] = None                      # 会话变化 -> 线索需重算

    summary, compressed = generator.compress_history(history)
    if compressed:
        session["summary"] = summary
        trace.append({
            "step": "M", "name": "多轮记忆压缩",
            "detail": "会话超过 %d 轮，历史压缩为摘要：%s" % (len(history), summary[:50] + "…"),
        })
    store.save(session)

    return {
        "session_id": session["id"],
        "reply": answer,
        "trace": trace,
        "intent": intent,
        "references": {
            "statutes": statute_result["results"],
            "cases": case_result["results"],
            "notice": "案例为演示用虚构样例，法条依据公开法律文本整理。",
        },
        "risk": risk_result,
    }


def get_lead(session):
    """B 端分析：带缓存，会话未变化时直接返回上一次的分析结果。"""
    from . import lead
    stamp = len(session.get("history", []))
    cached = session.get("lead_cache")
    if cached and cached.get("stamp") == stamp:
        return cached["data"]
    data = lead.analyze(session)
    if data is None:
        return None
    session["lead_cache"] = {"stamp": stamp, "data": data}
    store.save(session)
    return data

