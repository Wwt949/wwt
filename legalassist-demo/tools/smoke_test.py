"""端到端冒烟测试：模拟一次完整的 C 端咨询 -> B 端线索分析链路。

运行：  python tools/smoke_test.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))

from engine import pipeline, store  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

CONVERSATION = [
    "公司一直没跟我签劳动合同，我已经干了11个月了。",
    "而且他们拖欠我上个月的工资，社保也没交。",
    "我想辞职，这种情况能要二倍工资和经济补偿吗？仲裁时效是多久？",
    "我已经准备找律师了，这类案件法院一般怎么判？律师费大概多少？",
]


def main():
    store.reset()
    session = store.create(user_alias="测试用户-张三")
    print("会话 ID: %s\n" % session["id"])

    for i, msg in enumerate(CONVERSATION, 1):
        print("=" * 70)
        print("【第 %d 轮 · 用户】%s" % (i, msg))
        result = pipeline.handle_chat(session, msg)
        print("\n--- 工作流时序 ---")
        for step in result["trace"]:
            model = step.get("model")
            tag = " [%s]" % model["model_label"] if model else ""
            print("  %s%s  %s" % (step["step"], tag, step["name"]))
            print("      %s" % step["detail"])
        print("\n--- 回答（前 18 行）---")
        for line in result["reply"].splitlines()[:18]:
            print(line)
        print()

    print("=" * 70)
    print("【B 端 · 意向客户分析】")
    lead = pipeline.get_lead(store.get(session["id"]))
    print("  意向等级 : %s（%d 分）" % (lead["grade"], lead["score"]))
    print("  案件标签 : %s" % "、".join(lead["tags"]))
    print("  诉求拆解 : %s" % "、".join(lead["demands"]))
    print("  风险等级 : %s" % lead["risk"]["risk_level"])
    print("  评分明细 :")
    for d in lead["score_detail"]:
        print("      +%-3d %s" % (d["score"], d["factor"]))
    print("  跟进建议 :")
    for f in lead["followups"]:
        print("      - %s" % f)
    print("\n✅ 端到端链路跑通：C端咨询 -> 意图识别 -> 工具调用 -> 生成回答 -> B端线索")


if __name__ == "__main__":
    main()

