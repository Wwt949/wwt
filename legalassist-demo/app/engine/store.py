"""会话存储（对应 PPT 第 9 页数据层：用户与会话数据库 / 线索 CRM）。

Demo 用 JSON 文件落盘；生产环境替换为 MySQL / PostgreSQL + 向量库。
接口保持 repository 形态，便于后续换成真实数据库实现。
"""
import json
import os
import random
import threading
import time
import uuid
from datetime import datetime

from . import config

_LOCK = threading.Lock()


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _path(session_id):
    return os.path.join(config.SESSION_DIR, "%s.json" % session_id)


def _ensure_dir():
    os.makedirs(config.SESSION_DIR, exist_ok=True)


def create(user_alias=None):
    _ensure_dir()
    sid = "S" + time.strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:6]
    if not user_alias:
        user_alias = "消费者-%04d" % random.randint(1000, 9999)
    session = {
        "id": sid,
        "user_alias": user_alias,
        "created_at": _now(),
        "updated_at": _now(),
        "history": [],
        "turn_intents": [],
        "turn_traces": [],
        "key_facts": [],
        "summary": "",
        "follow_status": "待跟进",
        "lead_cache": None,
    }
    save(session)
    return session


def save(session):
    _ensure_dir()
    session["updated_at"] = _now()
    with _LOCK:
        with open(_path(session["id"]), "w", encoding="utf-8") as f:
            json.dump(session, f, ensure_ascii=False, indent=2)


def save_raw(session):
    """按 session 内已有时间戳落盘，不刷新 updated_at。

    供演示数据回填（把样例线索的时间分布在过去若干天）使用，
    普通写入请走 save()。
    """
    _ensure_dir()
    with _LOCK:
        with open(_path(session["id"]), "w", encoding="utf-8") as f:
            json.dump(session, f, ensure_ascii=False, indent=2)


def get(session_id):
    try:
        with open(_path(session_id), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def list_all():
    _ensure_dir()
    out = []
    for name in os.listdir(config.SESSION_DIR):
        if name.endswith(".json"):
            s = get(name[:-5])
            if s:
                out.append(s)
    out.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
    return out


def set_follow_status(session_id, status):
    session = get(session_id)
    if not session:
        return None
    session["follow_status"] = status
    save(session)
    return session


def reset():
    """清空演示数据。"""
    _ensure_dir()
    with _LOCK:
        for name in os.listdir(config.SESSION_DIR):
            if name.endswith(".json"):
                os.remove(os.path.join(config.SESSION_DIR, name))

