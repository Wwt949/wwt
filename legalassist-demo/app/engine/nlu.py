"""意图识别 + 法律实体抽取（PPT 第 6 页第 2 步、第 9 页 AI 能力层）。

这是「千问-Turbo」档位负责的部分：延迟优先的轻量分类任务。
"""
import re

CATEGORIES = {
    "labor": {"label": "劳动纠纷", "law_domain": "《劳动合同法》《劳动法》《劳动争议调解仲裁法》"},
    "marriage": {"label": "婚姻家事", "law_domain": "《民法典》婚姻家庭编"},
    "contract": {"label": "合同纠纷", "law_domain": "《民法典》合同编 / 总则编"},
    "loan": {"label": "民间借贷", "law_domain": "《民法典》合同编 + 民间借贷司法解释"},
    "other": {"label": "其他法律咨询", "law_domain": "通用民事法律"},
}

# 关键词 -> 权重。权重越高，命中后对该类别的判定贡献越大。
CATEGORY_KEYWORDS = {
    "labor": {
        "劳动合同": 3, "公司": 1, "用人单位": 3, "老板": 2, "工资": 3, "薪资": 2,
        "加班": 3, "加班费": 3, "辞退": 3, "开除": 3, "离职": 3, "辞职": 3,
        "社保": 3, "五险一金": 3, "经济补偿": 3, "赔偿金": 2, "试用期": 3,
        "劳动仲裁": 3, "欠薪": 3, "拖欠工资": 3, "工伤": 3, "调岗": 2,
        "被裁": 3, "裁员": 3, "入职": 2, "离职证明": 3, "n+1": 3,
    },
    "marriage": {
        "离婚": 4, "结婚": 2, "夫妻": 3, "婚姻": 3, "老公": 2, "老婆": 2,
        "丈夫": 2, "妻子": 2, "抚养权": 4, "孩子": 2, "子女": 3, "抚养费": 3,
        "财产分割": 4, "共同财产": 3, "婚前": 3, "彩礼": 3, "家暴": 4,
        "出轨": 3, "冷静期": 3, "起诉离婚": 4, "分居": 3, "继承": 2,
    },
    "contract": {
        "合同": 3, "协议": 2, "违约": 4, "违约金": 4, "签合同": 3, "解约": 3,
        "退款": 3, "退费": 3, "被骗": 3, "欺诈": 3, "货不对板": 3, "定金": 3,
        "订金": 3, "押金": 3, "甲方": 2, "乙方": 2, "履行": 2, "解除合同": 4,
        "服务合同": 3, "买卖": 2, "装修": 2, "预付卡": 3,
    },
    "loan": {
        "借钱": 4, "借款": 4, "欠钱": 4, "欠款": 3, "借条": 4, "欠条": 4,
        "民间借贷": 4, "利息": 3, "利率": 3, "高利贷": 4, "本金": 3,
        "还钱": 3, "不还钱": 4, "转账": 2, "担保": 3, "催收": 3,
    },
}

# 诉求类型：决定「维权路径」段落输出哪一条。
SUB_INTENTS = {
    "claim_money": {"label": "主张金钱给付", "kw": ["赔偿", "赔钱", "要钱", "还钱", "补偿", "赔我", "退还", "退款", "要回", "工资", "加班费", "欠款"]},
    "terminate": {"label": "解除关系 / 退出", "kw": ["离婚", "辞职", "离职", "解除合同", "退单", "解约", "退出", "不干了"]},
    "procedure": {"label": "程序与时效咨询", "kw": ["怎么办", "怎么起诉", "怎么告", "流程", "时效", "多久", "去哪里", "仲裁", "立案", "能不能告", "材料"]},
    "evidence": {"label": "证据咨询", "kw": ["证据", "聊天记录", "录音", "截图", "证明", "转账记录", "举证", "没有证据"]},
    "rights_confirm": {"label": "权利确认", "kw": ["合法吗", "合不合法", "算不算", "能不能", "有没有权利", "是否有效", "效力"]},
}

# 强意向信号：出现即表明用户已进入"准备行动/寻求委托"阶段。
STRONG_INTENT_KW = [
    "找律师", "请律师", "委托", "打官司", "起诉", "立案", "帮我写", "代理",
    "要多少钱", "律师费", "怎么收费", "面谈", "联系方式", "电话",
]

URGENCY_KW = ["马上", "立即", "已经", "明天", "这周", "急着", "紧急", "再不", "拖了"]


def _score_categories(text):
    scores = {cat: 0 for cat in CATEGORY_KEYWORDS}
    hits = {cat: [] for cat in CATEGORY_KEYWORDS}
    low = text.lower()
    for cat, kws in CATEGORY_KEYWORDS.items():
        for kw, weight in kws.items():
            if kw in low:
                scores[cat] += weight
                hits[cat].append(kw)
    return scores, hits


def extract_entities(text):
    """抽取法律实体：金额、时长、时间点、当事人称谓。"""
    entities = {"amount": [], "duration": [], "parties": [], "time_point": []}

    # 金额：10000元 / 3.5万 / 八千 / 1.2万元
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(万元|万|元|块)", text):
        num = float(m.group(1))
        unit = m.group(2)
        yuan = num * 10000 if unit in ("万", "万元") else num
        entities["amount"].append({"raw": m.group(0), "yuan": yuan})

    # 时长：3个月 / 两年 / 半年 / 11 个月
    for m in re.finditer(r"(\d+)\s*(个?月|年|天|周)", text):
        entities["duration"].append(m.group(0))
    for word, label in [("半年", "6个月"), ("两年", "2年"), ("一年", "1年"), ("三年", "3年")]:
        if word in text:
            entities["duration"].append(label)

    # 时间点
    for m in re.finditer(r"(去年|前年|今年|上个?月|上个月|\d{4}\s*年(?:\d{1,2}\s*月)?)", text):
        entities["time_point"].append(m.group(0).strip())

    # 当事人称谓
    for word in ["公司", "老板", "用人单位", "房东", "中介", "对方", "前夫", "前妻", "老公", "老婆", "朋友", "同事", "HR"]:
        if word in text:
            entities["parties"].append(word)

    return entities


def recognize(text, history=None):
    """意图识别主入口。返回结构化意图对象。"""
    scores, hits = _score_categories(text)
    # 多轮场景：历史会话的整体案件类型对当前轮次有一定先验权重
    if history:
        hist_text = " ".join(m.get("content", "") for m in history[-4:])
        hist_scores, _ = _score_categories(hist_text)
        for cat in scores:
            scores[cat] += int(hist_scores[cat] * 0.3)

    total = sum(scores.values())
    if total == 0:
        category = "other"
        confidence = 0.35
    else:
        category = max(scores, key=scores.get)
        confidence = round(min(0.98, scores[category] / max(total, 1) + 0.35), 2)

    sub_intent, sub_label = "procedure", SUB_INTENTS["procedure"]["label"]
    best_sub = 0
    for key, spec in SUB_INTENTS.items():
        hit = sum(1 for kw in spec["kw"] if kw in text)
        if hit > best_sub:
            best_sub, sub_intent, sub_label = hit, key, spec["label"]

    strong = [kw for kw in STRONG_INTENT_KW if kw in text]
    urgency = [kw for kw in URGENCY_KW if kw in text]

    return {
        "category": category,
        "category_label": CATEGORIES[category]["label"],
        "law_domain": CATEGORIES[category]["law_domain"],
        "confidence": confidence,
        "matched_keywords": hits.get(category, []),
        "category_scores": {k: v for k, v in scores.items() if v > 0},
        "sub_intent": sub_intent,
        "sub_intent_label": sub_label,
        "strong_intent_signals": strong,
        "urgency_signals": urgency,
        "entities": extract_entities(text),
    }

