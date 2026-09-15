"""Персональный login-токен для Mini App (когда initData пустой на части клиентов)."""

from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

from config import BOT_TOKEN, WEBAPP_URL

# Подпись токена — от токена бота. Не путать со старым общим ?dev=.
_LOGIN_SECRET = hashlib.sha256(f"yvy-login-v1:{BOT_TOKEN}".encode()).digest()
# Короткий TTL: старые «общие» ссылки (в т.ч. админские) быстро протухают.
# Новая кнопка из /start всегда выдаёт свежий токен.
LOGIN_TTL_SEC = 2 * 24 * 3600  # 48 часов


def make_login_token(tid: int, ttl: int = LOGIN_TTL_SEC) -> str:
    exp = int(time.time()) + int(ttl)
    payload = f"{int(tid)}.{exp}"
    sig = hmac.new(_LOGIN_SECRET, payload.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{payload}.{sig}"


def verify_login_token(token: str) -> int | None:
    if not token or not isinstance(token, str):
        return None
    parts = token.strip().split(".")
    if len(parts) != 3:
        return None
    tid_s, exp_s, sig = parts
    payload = f"{tid_s}.{exp_s}"
    expect = hmac.new(_LOGIN_SECRET, payload.encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(expect, sig):
        return None
    try:
        tid = int(tid_s)
        exp = int(exp_s)
    except ValueError:
        return None
    if tid <= 0:
        return None
    now = int(time.time())
    if exp < now or exp > now + LOGIN_TTL_SEC + 3600:
        return None
    return tid


def webapp_url_for(tid: int, **extra: str | int) -> str:
    """URL Mini App с персональным токеном этого пользователя."""
    token = make_login_token(tid)
    parts = urlsplit(WEBAPP_URL)
    q = dict(parse_qsl(parts.query, keep_blank_values=True))
    q["s"] = token
    for k, v in extra.items():
        if v is None:
            continue
        q[str(k)] = str(v)
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", urlencode(q), parts.fragment))
