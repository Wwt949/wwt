"""Function Calling 工具调用链（对应 PPT 第 10 页「工具体系」）。

工具一 法条检索  tool_search_statutes  触发：提问涉及具体法律问题时自动调用
工具二 案例匹配  tool_match_cases      触发：用户询问"类似案件怎么判 / 有没有先例"
工具三 风险评估  tool_assess_risk      触发：案情描述较完整时自动触发，B 端分析必调
"""
from . import rag
from .textutil import keyword_present

# ------------------------------------------------------------------ 证据清单库
EVIDENCE_CHECKLIST = {
    "labor": [
        ("书面劳动合同", ["劳动合同", "签了合同", "合同原件"]),
        ("工资流水 / 银行流水", ["工资流水", "银行流水", "流水", "发薪记录"]),
        ("考勤 / 打卡记录", ["考勤", "打卡", "钉钉", "考勤记录", "排班"]),
        ("工作沟通记录", ["微信", "钉钉", "企业微信", "聊天记录", "群聊", "邮件"]),
        ("解除 / 辞退通知", ["辞退通知", "解除通知", "通知书", "辞退邮件", "聊天通知"]),
        ("社保缴纳记录", ["社保记录", "社保缴纳", "缴费记录", "社保明细"]),
        ("劳动关系凭证", ["工牌", "工作证", "入职登记", "录用通知", "offer", "工服"]),
        ("录音 / 证人证言", ["录音", "录像", "证人", "同事作证"]),
    ],
    "marriage": [
        ("结婚证", ["结婚证", "登记结婚"]),
        ("分居证明", ["分居", "租房合同", "居委会", "居住证明"]),
        ("家暴证据", ["报警", "伤情", "验伤", "告诫书", "照片", "医院"]),
        ("过错证据", ["出轨", "聊天记录", "开房", "同居", "照片", "转账"]),
        ("财产凭证", ["房产证", "银行流水", "存款", "股权", "车辆", "公积金"]),
        ("子女相关材料", ["出生证明", "抚养", "学费", "疫苗", "就医"]),
        ("调解 / 沟通记录", ["调解", "协商记录", "微信", "短信"]),
    ],
    "contract": [
        ("合同 / 协议原件", ["合同", "协议", "订单", "原件", "扫描件"]),
        ("付款凭证", ["转账", "付款", "银行流水", "收据", "发票", "支付宝", "微信支付"]),
        ("沟通记录", ["微信", "聊天记录", "邮件", "短信", "电话录音"]),
        ("履行证据", ["送货单", "验收单", "签收", "照片", "视频", "物流"]),
        ("违约事实证据", ["违约", "逾期", "未交付", "质量", "检测报告", "截图"]),
        ("催告与送达凭证", ["催告", "通知函", "律师函", "EMS", "送达"]),
        ("损失证明", ["损失", "发票", "报价单", "评估报告", "费用"]),
    ],
    "loan": [
        ("借条 / 欠条原件", ["借条", "欠条", "借款协议", "借据"]),
        ("转账凭证", ["转账", "银行流水", "支付宝", "微信转账", "汇款", "流水"]),
        ("催收记录", ["催收", "催款", "要钱", "聊天记录", "通话录音", "短信"]),
        ("借款人身份信息", ["身份证", "身份信息", "姓名", "住址", "户籍"]),
        ("利息 / 还款约定", ["利息", "利率", "还款", "约定"]),
        ("担保材料", ["担保", "保证人", "抵押", "质押"]),
    ],
    "other": [
        ("书面材料", ["合同", "协议", "文件", "书面"]),
        ("沟通记录", ["微信", "聊天记录", "邮件", "录音"]),
        ("身份与关系证明", ["身份证", "关系证明"]),
    ],
}

# 时效提示：法律依据 + 年限（PPT 第 6 页「风险提示」环节）
LIMITATION = {
    "labor": ("劳动争议申请仲裁的时效期间为一年，自知道或应当知道权利被侵害之日起计算；劳动关系存续期间因拖欠劳动报酬发生争议的不受一年限制，但劳动关系终止后应在一年内提出。", 1),
    "contract": ("向人民法院请求保护民事权利的诉讼时效期间为三年；欺诈类撤销权应自知道或应当知道撤销事由之日起一年内行使。", 3),
    "loan": ("向人民法院请求保护民事权利的诉讼时效期间为三年，自知道或应当知道权利受到损害之日起计算。", 3),
    "marriage": ("离婚诉讼本身不受诉讼时效限制；但离婚后请求再次分割共同财产的，应在发现之日起三年内提出。", 3),
    "other": ("一般民事权利的诉讼时效期间为三年。", 3),
}

BASE_WIN_RATE = {"labor": 0.70, "marriage": 0.62, "contract": 0.66, "loan": 0.72, "other": 0.55}

# 主张事实抽取：用户很少直接说"我有工资流水"，而是陈述"公司拖欠我工资"。
# 这里把「否定/受损表述 + 对象词」识别为待证明的事实主张，供律师快速掌握案情。
# 格式：(主张标签, 必须出现的对象词 或 None, 触发词之一)
CLAIM_PATTERNS = [
    ("未签订书面劳动合同", "合同", ["没签", "未签", "没有签", "不给合同", "没给合同", "没有合同"]),
    ("被拖欠劳动报酬", "工资", ["拖欠", "没发", "不发", "克扣", "拖着", "欠着"]),
    ("未依法缴纳社会保险", "社保", ["没交", "未缴", "没缴", "不交", "没有缴"]),
    ("被违法解除劳动合同", None, ["违法辞退", "违法解除", "无故开除", "被开除", "被辞退", "让我走人"]),
    ("长时间加班未获加班费", "加班", ["加班费", "加班", "996", "没给钱"]),
    ("存在家庭暴力", None, ["家暴", "打我", "殴打", "虐待", "动手"]),
    ("对方存在婚外情 / 同居", None, ["出轨", "同居", "第三者", "外遇"]),
    ("因感情不和分居满两年", None, ["分居两年", "分居满两年", "分居2年", "分居满2年"]),
    ("对方违约未履行合同", None, ["违约", "没履行", "不履行", "没交付", "失联", "跑路", "不开工"]),
    ("借款到期未获偿还", None, ["借钱不还", "不还钱", "没还", "到期不还", "欠钱不还", "不还我", "不还了", "不还", "赖账", "催了"]),
    ("可能存在欺诈情形", None, ["被骗", "欺诈", "虚假承诺", "套路", "骗我", "虚假宣传"]),
    ("约定利息可能超过司法保护上限", None, ["月息", "3分", "三分", "高利贷", "利息"]),
    ("对方不同意离婚", None, ["不同意离婚", "不肯离", "不愿意离"]),
]


def extract_claims(corpus):
    """抽取用户主张的、需要通过证据证明的事实。

    两类命中方式：
      1. 显式触发词直接命中（如"拖欠"+"工资"）
      2. 对象词被否定标记修饰（如"没跟我签劳动合同" -> 未签订书面劳动合同）
    第 2 类正是用户最自然的表达方式，也是关键词字面匹配最容易漏掉的部分。
    """
    claims = []
    for label, anchor, triggers in CLAIM_PATTERNS:
        explicit = any(t in corpus for t in triggers)
        if anchor is None:
            hit = explicit
        else:
            appears = anchor in corpus
            negated = appears and not keyword_present(corpus, anchor)
            hit = appears and (explicit or negated)
        if hit:
            claims.append(label)
    return claims


# ---------------------------------------------------------------------- 工具一
def tool_search_statutes(intent, user_text, top_k=4):
    """入参：案件类型 + 关键词 -> 向量检索 Top-K 法条 -> 返回条款原文与司法解释。"""
    results = rag.search_statutes(user_text, category=intent["category"], top_k=top_k)
    return {
        "tool": "search_statutes",
        "tool_name": "法条检索",
        "trigger": "提问涉及具体法律问题，自动调用",
        "input": {"category": intent["category_label"], "keywords": intent["matched_keywords"][:6]},
        "hit_count": len(results),
        "results": results,
        "evidence": [r["matched_keywords"] for r in results],
    }


# ---------------------------------------------------------------------- 工具二
CASE_TRIGGER_KW = ["类似", "怎么判", "先例", "判例", "案例", "别人", "法院会", "能赢吗", "胜诉"]


def should_match_cases(user_text, turn_index):
    """触发条件：用户明确询问类似案件裁判结果时调用（PPT 原话）。"""
    return any(kw in user_text for kw in CASE_TRIGGER_KW) or turn_index >= 2


def tool_match_cases(intent, user_text, top_k=2):
    """入参：案情摘要 + 争议焦点 -> 检索同类裁判文书 -> 返回案号、裁判要旨与判决结果。"""
    summary = user_text
    focus = intent["matched_keywords"][:5]
    results = rag.search_cases(summary, focus, category=intent["category"], top_k=top_k)
    return {
        "tool": "match_cases",
        "tool_name": "案例匹配",
        "trigger": "用户询问类似案件裁判结果，自动调用",
        "input": {"summary": summary[:60], "focus": focus},
        "hit_count": len(results),
        "results": results,
        "focus": focus,
    }


# ---------------------------------------------------------------------- 工具三
ADVERSE_KW = ["没有证据", "没证据", "找不到", "没有书面", "口头", "没签", "丢了", "没保留",
              "过期", "很久", "两年前", "三年前", "不清楚"]
STRONG_ADVERSE_KW = ["没签劳动合同", "没有合同", "口头约定", "现金发放", "没有流水"]


def tool_assess_risk(intent, user_text, history_text=""):
    """入参：证据清单 + 案件事实 -> 规则引擎 + LLM 联合评估 -> 返回风险等级与胜诉概率区间。"""
    category = intent["category"]
    checklist = EVIDENCE_CHECKLIST.get(category, EVIDENCE_CHECKLIST["other"])
    corpus = (user_text + " " + history_text).lower()

    found, missing = [], []
    for name, kws in checklist:
        # 否定感知：用户说"没签劳动合同"时，不应判定为"已具备书面劳动合同"
        if any(keyword_present(corpus, kw) for kw in kws):
            found.append(name)
        else:
            missing.append(name)

    ratio = len(found) / max(len(checklist), 1)
    prob = BASE_WIN_RATE.get(category, 0.55) + (ratio - 0.5) * 0.40

    risks = []
    # 1) 证据不足
    if ratio < 0.4:
        risks.append({"level": "高", "point": "关键证据缺失严重（当前仅识别到 %d/%d 项）" % (len(found), len(checklist)),
                      "advice": "优先固定证据：" + "、".join(missing[:3])})
    elif ratio < 0.7:
        risks.append({"level": "中", "point": "部分证据尚未固定（%d/%d 项）" % (len(found), len(checklist)),
                      "advice": "建议补充：" + "、".join(missing[:3])})
    # 2) 时效风险
    limitation_text, years = LIMITATION.get(category, LIMITATION["other"])
    if any(kw in corpus for kw in ["两年前", "三年前", "四年前", "多年前", "去年"]):
        risks.append({"level": "高", "point": "存在超过 %d 年时效的表述，可能面临时效抗辩" % years,
                      "advice": limitation_text})
        prob -= 0.10
    # 3) 举证形式瑕疵
    if any(kw in corpus for kw in STRONG_ADVERSE_KW):
        risks.append({"level": "中", "point": "存在口头约定 / 无书面凭证情形，举证难度上升",
                      "advice": "通过聊天记录、录音、转账备注、证人证言等间接证据补强"})
        prob -= 0.06
    # 4) 对方抗辩预判
    if any(kw in corpus for kw in ADVERSE_KW):
        risks.append({"level": "中", "point": "对方可能提出相应对抗主张",
                      "advice": "提前准备反驳证据与书面说明，明确举证责任分配"})

    prob = max(0.30, min(0.92, prob))
    if prob >= 0.72:
        level = "低"
    elif prob >= 0.55:
        level = "中"
    else:
        level = "高"

    return {
        "tool": "assess_risk",
        "tool_name": "风险评估",
        "trigger": "案情描述较完整，自动触发（B 端分析必调）",
        "input": {"category": intent["category_label"], "evidence_identified": len(found)},
        "risk_level": level,
        "win_probability": {"low": round(prob - 0.08, 2), "mid": round(prob, 2), "high": round(prob + 0.08, 2)},
        "evidence": {"found": found, "missing": missing, "coverage": round(ratio, 2)},
        "claims": extract_claims(corpus),
        "risks": risks,
        "limitation_advice": limitation_text,
    }

