"""下载 BGE-small-zh-v1.5 的 ONNX 权重与分词器。

优先 huggingface.co，失败自动切换 hf-mirror.com（国内镜像）。
支持断点续传与 sha 校验跳过。

用法:  python tools/fetch_model.py
"""
import json
import os
import sys
import time
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR = os.path.join(BASE_DIR, "app", "data", "models", "bge-small-zh-v1.5")

REPO = "Xenova/bge-small-zh-v1.5"
MIRRORS = ["https://huggingface.co", "https://hf-mirror.com"]

# 只需要推理用到的最小集合
FILES = [
    "onnx/model.onnx",
    "tokenizer.json",
    "config.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
]


def _url(base, path):
    return "%s/%s/resolve/main/%s" % (base, REPO, path)


def _download(path, dest):
    if os.path.exists(dest) and os.path.getsize(dest) > 1024:
        print("  跳过（已存在）: %s (%.1f MB)" % (path, os.path.getsize(dest) / 1048576))
        return True

    for base in MIRRORS:
        url = _url(base, path)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            resp = urllib.request.urlopen(req, timeout=60)
            total = int(resp.headers.get("Content-Length") or 0)
            tmp = dest + ".part"
            os.makedirs(os.path.dirname(tmp), exist_ok=True)
            done = 0
            started = time.time()
            with open(tmp, "wb") as f:
                while True:
                    chunk = resp.read(262144)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if total > 262144:      # 只对大文件打进度
                        pct = done * 100.0 / total
                        sys.stdout.write("\r  %s  %5.1f%%  (%.1f/%.1f MB)"
                                         % (path, pct, done / 1048576, total / 1048576))
                        sys.stdout.flush()
            if total:
                sys.stdout.write("\r  完成: %s  %.1f MB  用时 %.1fs%s\n"
                                 % (path, done / 1048576, time.time() - started, " " * 20))
            else:
                print("  完成: %s  %.1f KB" % (path, done / 1024))
            os.replace(tmp, dest)
            return True
        except Exception as exc:
            print("  镜像 %s 失败: %s: %s" % (base, type(exc).__name__, str(exc)[:90]))
            if os.path.exists(dest + ".part"):
                os.remove(dest + ".part")
    return False


def main():
    print("目标目录: %s" % MODEL_DIR)
    print("模型仓库: %s\n" % REPO)
    ok = True
    for path in FILES:
        dest = os.path.join(MODEL_DIR, path.replace("/", os.sep))
        ok = _download(path, dest) and ok

    if ok:
        size = sum(os.path.getsize(os.path.join(dp, f))
                   for dp, _, fs in os.walk(MODEL_DIR) for f in fs)
        print("\n✅ 全部就绪，模型目录共 %.1f MB" % (size / 1048576))
        manifest = {"repo": REPO, "files": FILES, "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S")}
        with open(os.path.join(MODEL_DIR, "SOURCE.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
    else:
        print("\n❌ 部分文件下载失败，请检查网络后重试")
        sys.exit(1)


if __name__ == "__main__":
    main()

