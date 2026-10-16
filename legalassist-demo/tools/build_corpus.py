"""构建法律知识库：从公开法律文本仓库抽取「条」级语料。

数据来源（均为公开可获取的 GitHub 仓库，只做解析与结构化，不修改原文）：
  risshun/Chinese_Laws   —— 民法典 / 劳动合同法 / 劳动法（按编、章、条结构化）
  LawRefBook/Laws        —— 工伤保险条例 / 劳动争议调解仲裁法 / 民间借贷司法解释 等

两个仓库的 Markdown 体例不同，用 style 区分解析器：
  bold        **第一千零七十九条**正文
  plain       第一千零七十九条 正文

输出 app/data/law_kb.json。

用法:
    python tools/build_corpus.py              # 增量构建（已下载则用缓存）
    python tools/build_corpus.py --refresh    # 强制重新下载
"""
import argparse
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "app", "data")
CACHE_DIR = os.path.join(DATA_DIR, "corpus_cache")
OUT_PATH = os.path.join(DATA_DIR, "law_kb.json")

REPOS = {
    "risshun": "https://raw.githubusercontent.com/risshun/Chinese_Laws/master/",
    "lawrefbook": "https://raw.githubusercontent.com/LawRefBook/Laws/master/",
}

# 生效日期补全表。源文件名里带的是「公布/修订日」，与施行日并不总是同一天，
# 因此这里只对确知的另行标注；查不到的留空，绝不猜测。
EFFECTIVE_DATES = {
    "工伤保险条例": ("2010-12-20", "2011-01-01"),
    "劳动争议调解仲裁法": ("2007-12-29", "2008-05-01"),
    "民间借贷司法解释": ("2020-12-29", "2021-01-01"),
}

# ---------------------------------------------------------------- 采集清单
# ranges: [(起, 止)] 收录条号区间；None 表示全量。
SOURCES = [
    {
        "repo": "risshun", "style": "bold",
        "file": "基本法律/中华人民共和国民法典.md",
        "short": "民法典",
        "name": "《中华人民共和国民法典》",
        "category": "contract",
        "effective_date": "2021-01-01",
        "status": "现行有效",
        "note": "2020 年 5 月 28 日通过，自 2021 年 1 月 1 日起施行；同时废止婚姻法、合同法等九部法律。",
        # 只取与业务相关的编：总则（法律行为效力/诉讼时效）、合同编、婚姻家庭编、
        # 侵权责任编（损害赔偿，主要服务家暴/人身伤害场景）。物权、继承等编不收。
        "ranges": [(137, 157), (176, 204), (463, 988), (1040, 1118), (1164, 1188)],
        "book_category": {"总则": "contract", "合同": "contract",
                          "婚姻家庭": "marriage", "侵权责任": "marriage"},
    },
    {
        "repo": "risshun", "style": "bold",
        "file": "非基本法律/中华人民共和国劳动合同法.md",
        "short": "劳动合同法", "name": "《中华人民共和国劳动合同法》",
        "category": "labor", "effective_date": "2013-07-01", "status": "现行有效",
        "note": "2007 年 6 月 29 日通过，2012 年 12 月 28 日修正，自 2013 年 7 月 1 日起施行。",
        "ranges": None,
    },
    {
        "repo": "risshun", "style": "bold",
        "file": "非基本法律/中华人民共和国劳动法.md",
        "short": "劳动法", "name": "《中华人民共和国劳动法》",
        "category": "labor", "effective_date": "2018-12-29", "status": "现行有效",
        "note": "1994 年 7 月 5 日通过，2018 年 12 月 29 日第二次修正。",
        "ranges": None,
    },
    {
        "repo": "lawrefbook", "style": "plain",
        "file": "行政法规/工伤保险条例(2010-12-20).md",
        "short": "工伤保险条例", "name": "《工伤保险条例》",
        "category": "labor", "status": "现行有效",
        "note": "2003 年 4 月 27 日国务院令第 375 号公布，2010 年 12 月 20 日修订。",
        "ranges": None,
    },
    {
        "repo": "lawrefbook", "style": "plain",
        "file": "诉讼与非诉讼程序法/劳动争议调解仲裁法(2007-12-29).md",
        "short": "劳动争议调解仲裁法", "name": "《中华人民共和国劳动争议调解仲裁法》",
        "category": "labor", "status": "现行有效",
        "note": "2007 年 12 月 29 日通过，自 2008 年 5 月 1 日起施行；劳动仲裁不收费，且是起诉的前置程序。",
        "ranges": None,
    },
    {
        "repo": "lawrefbook", "style": "plain",
        "file": "司法解释/最高人民法院关于审理民间借贷案件适用法律若干问题的规定(2020-12-29).md",
        "short": "民间借贷司法解释", "name": "《最高人民法院关于审理民间借贷案件适用法律若干问题的规定》",
        "category": "loan", "status": "现行有效",
        "note": "法释〔2020〕17 号，2020 年 12 月 29 日修正，自 2021 年 1 月 1 日起施行。",
        "ranges": None,
    },
]


# ------------------------------------------------------------- 中文数字解析
CN_DIGITS = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
             "六": 6, "七": 7, "八": 8, "九": 9,
             "〇": 0, "两": 2}
CN_UNITS = {"十": 10, "百": 100, "千": 1000}


def cn2int(text):
    """中文数字转阿拉伯数字：『一千零七十九』-> 1079。"""
    total = section = number = 0
    for ch in text:
        if ch in CN_DIGITS:
            number = CN_DIGITS[ch]
        elif ch in CN_UNITS:
            section += (number or 1) * CN_UNITS[ch]
            number = 0
        elif ch == "万":
            total += (section + number) * 10000
            section = number = 0
    return total + section + number


# ------------------------------------------------------------------ 下载
def download(repo, rel_path, refresh=False):
    os.makedirs(CACHE_DIR, exist_ok=True)
    dest = os.path.join(CACHE_DIR, repo, rel_path.replace("/", os.sep))
    if os.path.exists(dest) and os.path.getsize(dest) > 512 and not refresh:
        with io.open(dest, encoding="utf-8") as f:
            return f.read()
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    url = REPOS[repo] + urllib.parse.quote(rel_path)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    text = urllib.request.urlopen(req, timeout=90).read().decode("utf-8", "replace")
    with io.open(dest, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return text


# ------------------------------------------------------------------ 解析器
HEAD_RE = re.compile(r"^(#{1,4})\s*(.+?)\s*$")
BOLD_ART_RE = re.compile(r"\*\*(第[零一二三四五六七八九十百千万〇两]+条)\*\*")
# plain 体例：条号必须出现在行首，避免命中正文里的「依照本条例第二十条规定」式引用
PLAIN_ART_RE = re.compile(r"^第([零一二三四五六七八九十百千万〇两]+)条\s*(.*)$")


def _clean(text):
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)     # 去 markdown 链接
    text = text.replace("</br>", " ").replace("<br>", " ")
    return re.sub(r"\s+", " ", text).strip()


class _Collector:
    """把逐行解析出的条目按「编/章」路径归集，统一做清洗与编号。"""

    def __init__(self, source):
        self.src = source
        self.entries = []
        self.path = {"编": "", "章": ""}
        self.cur = None

    def flush(self):
        if self.cur:
            body = _clean(self.cur["body"])
            if body:
                self.cur["text"] = body
                self.entries.append(self.cur)
            self.cur = None

    def open(self, article, num, body=""):
        self.flush()
        self.cur = {
            "article": article, "num": num, "body": body,
            "law": self.src["name"], "short": self.src["short"],
            "section": " / ".join(v for v in self.path.values() if v),
            "book": self.path["编"],
        }

    def feed(self, line):
        if self.cur:
            self.cur["body"] += line


def parse_bold(text, source):
    """risshun 体例：**第X条**正文，支持一编多章。"""
    col = _Collector(source)
    lines = text.split("\n")
    for raw in lines:
        line = raw.strip()
        if not line:
            col.feed("\n")
            continue

        head = HEAD_RE.match(line)
        if head and not BOLD_ART_RE.search(line):
            title = _clean(head.group(2))
            if "分编" in title[:8]:
                col.path["章"] = ""
            elif "编" in title[:6] and title.startswith("第"):
                col.path = {"编": title, "章": ""}
            elif "章" in title[:6] and title.startswith("第"):
                col.path["章"] = title
            col.flush()
            continue

        found = BOLD_ART_RE.findall(line)
        if found:
            pieces = BOLD_ART_RE.sub("\x00", line).split("\x00")
            for idx, art in enumerate(found):
                num = cn2int(art.replace("第", "").replace("条", ""))
                col.open(art, num, (pieces[idx + 1] if idx + 1 < len(pieces) else "").strip())
            continue

        col.feed(line)
    col.flush()
    return col.entries


def parse_plain(text, source):
    """LawRefBook 体例：行首『第X条 正文』，后续空行分段仍属同一条。"""
    col = _Collector(source)
    for raw in text.split("\n"):
        line = raw.strip()
        if not line or line.startswith("<!--") or line.startswith(">"):
            col.feed("\n")
            continue

        head = HEAD_RE.match(line)
        if head:
            title = _clean(head.group(2))
            if head.group(1) == "#":                 # 一级标题 = 法律名，正文尚未开始
                col.flush()
                continue
            if "章" in title[:6] and title.startswith("第"):
                col.path["章"] = title
            col.flush()
            continue

        m = PLAIN_ART_RE.match(line)
        if m:
            num = cn2int(m.group(1))
            col.open("第%s条" % m.group(1), num, m.group(2).strip())
            continue

        col.feed(line)
    col.flush()
    return col.entries


PARSERS = {"bold": parse_bold, "plain": parse_plain}


def build_entry(src, e):
    """把解析结果规范化成知识库条目。"""
    cat = src["category"]
    for book_key, book_cat in (src.get("book_category") or {}).items():
        if book_key in e["book"]:
            cat = book_cat
            break

    published, effective = EFFECTIVE_DATES.get(src["short"], ("", ""))
    title = e["section"].split("/")[-1].strip() if e["section"] else ""
    title = re.sub(r"^第[零一二三四五六七八九十百千万]+章\s*", "", title)
    return {
        "id": "%s-%d" % (src["short"], e["num"]),
        "category": cat,
        "law": e["law"],
        "law_short": src["short"],
        "article": e["article"],
        "article_num": e["num"],
        "title": title or e["article"],
        "section_path": e["section"],
        "text": e["text"],
        "keywords": [],
        "source": "github.com/%s" % ("risshun/Chinese_Laws" if src["repo"] == "risshun"
                                     else "LawRefBook/Laws"),
        "status": src.get("status", ""),
        "published_date": published,
        "effective_date": effective or src.get("effective_date", ""),
        "note": src.get("note", ""),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="强制重新下载源文件")
    args = ap.parse_args()

    print("=" * 70)
    print("  构建法律知识库")
    print("=" * 70)

    all_entries = []
    for src in SOURCES:
        print("\n[%s] %s" % (src["repo"], src["file"]))
        try:
            text = download(src["repo"], src["file"], args.refresh)
        except Exception as exc:
            print("   ❌ 获取失败: %s: %s  —— 跳过，不影响其余语料"
                  % (type(exc).__name__, str(exc)[:90]))
            continue

        parsed = PARSERS[src["style"]](text, src)
        print("   解析出 %d 条" % len(parsed))
        if src.get("ranges"):
            parsed = [e for e in parsed
                      if any(lo <= e["num"] <= hi for lo, hi in src["ranges"])]
            print("   按编章范围筛选后保留 %d 条" % len(parsed))
        all_entries += [build_entry(src, e) for e in parsed]

    # 去重：同一「法律 + 条号」只保留一条（不同来源可能重复收录）
    seen, dedup = set(), []
    for e in all_entries:
        key = (e["law_short"], e["article"])
        if key not in seen:
            seen.add(key)
            dedup.append(e)
    if len(dedup) != len(all_entries):
        print("\n[去重] 移除 %d 条重复条目" % (len(all_entries) - len(dedup)))
    all_entries = dedup

    all_entries.sort(key=lambda e: (e["law_short"], e["article_num"]))
    kb = {
        "version": time.strftime("%Y.%m"),
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "sources": ["github.com/risshun/Chinese_Laws", "github.com/LawRefBook/Laws"],
        "notice": ("法条正文取自公开法律文本仓库并做结构化处理，供检索演示使用。"
                   "正式法律事务请以国家法律法规数据库（flk.npc.gov.cn）发布的正式文本为准。"),
        "entries": all_entries,
    }
    with io.open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(kb, f, ensure_ascii=False, indent=1)

    from collections import Counter
    print("\n" + "=" * 70)
    print("  输出: %s" % OUT_PATH)
    print("  总计: %d 条" % len(all_entries))
    print("  按法律:")
    for law, n in Counter(e["law_short"] for e in all_entries).most_common():
        print("     %-22s %4d 条" % (law, n))
    print("  按案件类型:")
    for cat, n in Counter(e["category"] for e in all_entries).most_common():
        print("     %-22s %4d 条" % (cat, n))
    short = [e["id"] for e in all_entries if len(e["text"]) < 10]
    print("  %s 正文过短的条目 %d 个%s"
          % ("⚠️" if short else "✅", len(short), (": " + str(short[:6])) if short else ""))
    print("=" * 70)


if __name__ == "__main__":
    main()

