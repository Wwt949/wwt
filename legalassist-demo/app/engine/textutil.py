"""中文文本匹配工具：否定感知的关键词命中 + 字符二元组。"""
import re

# 出现在关键词之前的否定/缺失标记。命中即认为"该事实不存在"，
# 避免把「公司没跟我签劳动合同」误判为「已具备书面劳动合同」。
NEGATION_MARKERS = ["没有", "没", "未", "无", "不", "缺", "丢", "找不到", "找不到", "从未", "无法提供"]
NEGATION_WINDOW = 8

# 含「不」但并不表否定的常见搭配。法律咨询里「能不能要…」「是否可以…」极常见，
# 若一律当成否定，会把「能不能要二倍工资」误判为"没有二倍工资"，
# 导致证据识别和案例召回同时漏判。这是启发式的补丁，真正的否定识别需要句法分析。
NON_NEGATING_PATTERNS = ["能不能", "是否能", "是否", "不仅", "不但", "不过",
                         "不同", "不论", "不管", "不如", "不菲"]

# 连续汉字 / 字母 / 数字构成一个「语段」。二元组只在语段内部取。
_RUN_RE = re.compile(r"[一-鿿A-Za-z0-9]+")


def _negated(prefix):
    """前缀里是否存在真正的否定意义（先剔除「能不能」这类非否定的「不」）。"""
    for pat in NON_NEGATING_PATTERNS:
        prefix = prefix.replace(pat, "")
    return any(neg in prefix for neg in NEGATION_MARKERS)


def keyword_present(text, kw):
    """关键词是否"肯定地"出现（命中且前面没有否定标记）。"""
    kw = kw.lower()
    start = 0
    while True:
        idx = text.find(kw, start)
        if idx < 0:
            return False
        if not _negated(text[max(0, idx - NEGATION_WINDOW):idx]):
            return True
        start = idx + 1


def bigrams(text):
    """字符二元组集合，用于近似语义重合度计算。

    只在连续语段内部取，不跨标点。早期版本只去空白，会产出「面，劳」→「面劳」
    这类跨标点的无意义组合：它们在语料里极稀有，IDF 反而很高，会把噪声当成
    强信号抬高分数。
    """
    grams = set()
    for run in _RUN_RE.findall(text or ""):
        for i in range(len(run) - 1):
            grams.add(run[i:i + 2])
    return grams

