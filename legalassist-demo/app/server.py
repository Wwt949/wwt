"""智能律询通 · 端到端 Demo 服务端。

零第三方依赖（仅 Python 标准库），对应 PPT 第 9 页四层架构中的
「接入层 + 应用服务层」：把 C 端咨询入口、B 端律师工作台 API 暴露为 HTTP 接口。

启动：  python app/server.py --port 8000
"""
import argparse
import json
import os
import sys
import urllib.parse
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from engine import config, embed, llm, pipeline, rag, store, vector_index

# 控制台在中文 Windows 上默认 GBK，避免打印中文时抛 UnicodeEncodeError
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "LegalAssistDemo/1.0"

    # ---------------------------------------------------------------- 基础输出
    def _send(self, status, body, content_type="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError):
            pass

    def _json(self, data, status=200):
        self._send(status, json.dumps(data, ensure_ascii=False))

    def _error(self, message, status=400):
        self._json({"ok": False, "error": message}, status)

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        raw = self.rfile.read(length).decode("utf-8", "replace")
        try:
            return json.loads(raw)
        except ValueError:
            return {}

    def log_message(self, fmt, *args):
        # 精简访问日志
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    # -------------------------------------------------------------------- 路由
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path, query = parsed.path, urllib.parse.parse_qs(parsed.query)

        if path == "/api/health":
            return self._json({
                "ok": True,
                "llm_mode": config.LLM_MODE,
                "models": {k: v["label"] for k, v in config.MODEL_TIERS.items()},
                "kb": rag.kb_stats(),
                "embedder": embed.EMBEDDER.info(),
                "indexes": vector_index.all_info(),
            })

        if path == "/api/router/stats":
            return self._json({"ok": True, "stats": llm.CLIENT.routing_stats(),
                               "recent": llm.CLIENT.call_log[-20:]})

        if path == "/api/leads":
            return self._leads(query)

        if path == "/api/sessions":
            items = []
            for s in store.list_all():
                lead = pipeline.get_lead(s)
                items.append({
                    "session_id": s["id"],
                    "user_alias": s.get("user_alias"),
                    "turns": sum(1 for m in s.get("history", []) if m["role"] == "user"),
                    "updated_at": s.get("updated_at"),
                    "grade": lead["grade"] if lead else "-",
                    "score": lead["score"] if lead else 0,
                    "tags": lead["tags"][:3] if lead else [],
                    "follow_status": s.get("follow_status", "待跟进"),
                })
            return self._json({"ok": True, "items": items})

        if path.startswith("/api/session/"):
            sid = path.rsplit("/", 1)[-1]
            session = store.get(sid)
            if not session:
                return self._error("会话不存在", 404)
            return self._json({"ok": True, "session": session, "lead": pipeline.get_lead(session)})

        # ---------------------------------------------------------- 静态资源
        return self._static(path)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        body = self._body()

        if path == "/api/session/new":
            session = store.create(body.get("user_alias"))
            return self._json({"ok": True, "session_id": session["id"],
                               "user_alias": session["user_alias"]})

        if path == "/api/chat":
            sid = body.get("session_id")
            message = (body.get("message") or "").strip()
            if not message:
                return self._error("message 不能为空")
            session = store.get(sid) if sid else None
            if session is None:
                session = store.create()
            result = pipeline.handle_chat(session, message)
            return self._json({"ok": True, **result})

        if path == "/api/leads/analyze":
            session = store.get(body.get("session_id"))
            if not session:
                return self._error("会话不存在", 404)
            session["lead_cache"] = None
            lead = pipeline.get_lead(session)
            if lead is None:
                return self._error("该会话暂无有效咨询内容，无法生成线索")
            return self._json({"ok": True, "lead": lead})

        if path == "/api/leads/status":
            session = store.set_follow_status(body.get("session_id"), body.get("status", "待跟进"))
            if not session:
                return self._error("会话不存在", 404)
            return self._json({"ok": True, "follow_status": session["follow_status"]})

        if path == "/api/leads/note":
            session = store.get(body.get("session_id"))
            if not session:
                return self._error("会话不存在", 404)
            session["follow_note"] = (body.get("note") or "").strip()
            store.save(session)
            return self._json({"ok": True, "follow_note": session["follow_note"]})

        if path == "/api/demo/seed":
            return self._seed()

        if path == "/api/admin/reset":
            store.reset()
            return self._json({"ok": True, "message": "演示数据已清空"})

        return self._error("未知接口：%s" % path, 404)

    # ---------------------------------------------------------------- 演示数据
    def _seed(self):
        """按 data/demo_seed.json 生成演示线索。

        每条样例咨询都真实走一遍 C 端流水线（意图识别 → 检索 → 生成 → 风险），
        再回填时间戳，使工作台的今日 / 近7日统计具备真实分布。
        仅清理上一次生成的演示数据（demo_seed 标记），不影响真实咨询产生的会话。
        """
        spec_path = os.path.join(config.DATA_DIR, "demo_seed.json")
        try:
            with open(spec_path, "r", encoding="utf-8") as f:
                spec = json.load(f)
        except (OSError, ValueError) as exc:
            return self._error("演示数据集不可用：%s" % exc, 500)

        removed = 0
        for s in store.list_all():
            if s.get("demo_seed"):
                try:
                    os.remove(os.path.join(config.SESSION_DIR, "%s.json" % s["id"]))
                    removed += 1
                except OSError:
                    pass

        created = 0
        for item in spec.get("sessions", []):
            session = store.create(item.get("alias"))
            for question in item.get("turns", []):
                pipeline.handle_chat(session, question)
            session["demo_seed"] = True
            session["follow_status"] = item.get("follow_status", "待跟进")
            session["follow_note"] = item.get("follow_note", "")
            _backdate(session, item.get("days_ago", 0))
            store.save_raw(session)
            created += 1

        return self._json({"ok": True, "created": created, "removed": removed,
                           "message": "已生成 %d 条演示线索" % created})

    # -------------------------------------------------------------- B 端线索池
    def _leads(self, query):
        category = (query.get("category") or [""])[0]
        grade = (query.get("grade") or [""])[0]
        status = (query.get("status") or [""])[0]

        items = []
        for s in store.list_all():
            lead = pipeline.get_lead(s)
            if lead is None:
                continue
            if grade and lead["grade"] != grade:
                continue
            if status and lead["follow_status"] != status:
                continue
            if category:
                labels = {"labor": "劳动纠纷", "marriage": "婚姻家事",
                          "contract": "合同纠纷", "loan": "民间借贷", "other": "其他法律咨询"}
                if labels.get(category, category) not in lead["tags"]:
                    continue
            items.append(lead)

        items.sort(key=lambda x: ({"高": 3, "中": 2, "低": 1}[x["grade"]], x["score"]), reverse=True)
        counts = {"高": 0, "中": 0, "低": 0}
        for lead in items:
            counts[lead["grade"]] += 1
        return self._json({"ok": True, "items": items, "counts": counts, "total": len(items)})

    # ------------------------------------------------------------------ 静态文件
    def _static(self, path):
        if path in ("/", ""):
            path = "/index.html"
        rel = path.lstrip("/").replace("\\", "/")
        # 目录穿越防护
        full = os.path.normpath(os.path.join(config.WEB_DIR, rel))
        if not full.startswith(os.path.normpath(config.WEB_DIR)):
            return self._error("非法路径", 403)
        if not os.path.isfile(full):
            return self._error("资源不存在：%s" % path, 404)
        ext = os.path.splitext(full)[1].lower()
        with open(full, "rb") as f:
            data = f.read()
        return self._send(200, data, CONTENT_TYPES.get(ext, "application/octet-stream"))


def _backdate(session, days_ago, hour=10, minute=24):
    """把会话时间回填到 days_ago 天前的 10:24（与交互稿一致），用于演示统计分布。"""
    stamp = (datetime.now() - timedelta(days=days_ago)).replace(
        hour=hour, minute=minute, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
    session["created_at"] = stamp
    session["updated_at"] = stamp
    for msg in session.get("history", []):
        msg["ts"] = stamp


def main():
    parser = argparse.ArgumentParser(description="智能律询通 Demo 服务端")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--open", action="store_true", help="启动后自动打开浏览器")
    args = parser.parse_args()

    os.makedirs(config.SESSION_DIR, exist_ok=True)
    stats = rag.kb_stats()

    print("=" * 62)
    print("  智能律询通 · 端到端 Demo  (LEGAL-AGENT MVP v1.0)")
    print("=" * 62)
    print("  访问地址 : http://%s:%d" % (args.host, args.port))
    print("  模型模式 : %s" % config.LLM_MODE)
    print("  知识库   : 法条 %d 条 / 案例 %d 条" % (stats["statutes"], stats["cases"]))

    # 向量索引预热：放在起服务之前，避免首个用户请求承担建库耗时。
    # 首次运行需编码全部法条（数十秒），之后走磁盘缓存（毫秒级）。
    print("  向量后端 : %s（%s）" % (embed.EMBEDDER.name,
                                    "语义检索" if embed.EMBEDDER.is_semantic else "词面兜底"))
    if embed.EMBEDDER.fallback_reason:
        print("  ⚠️  降级原因: %s" % embed.EMBEDDER.fallback_reason)
    print("  正在预热向量索引 ...")
    warm = vector_index.prewarm()
    print("  索引就绪 : %d 条 %d 维 [%s] 耗时 %dms"
          % (warm["statutes"]["entries"], warm["statutes"]["dim"],
             warm["statutes"]["cache"], warm["ms"]))
    print("  数据目录 : %s" % config.SESSION_DIR)
    print("  按 Ctrl+C 停止服务")
    print("=" * 62)

    server = ThreadingHTTPServer((args.host, args.port), Handler)

    if args.open:
        import threading
        import webbrowser
        url = "http://%s:%d" % (args.host, args.port)
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
        server.server_close()


if __name__ == "__main__":
    main()

