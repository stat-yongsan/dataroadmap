"""Hosted mode: public immutable example, private app APIs, short-lived signed admin cookie."""
import hashlib
import hmac
import json
import secrets
import time
from urllib.parse import urlsplit

from fastapi.responses import JSONResponse

from . import settings

COOKIE = "roadmap_admin"
_failures = {}


def session_token(at=None):
    stamp = str(int(time.time() if at is None else at))
    signature = hmac.new(settings.ADMIN_PASSWORD.encode(), stamp.encode(), hashlib.sha256).hexdigest()
    return f"{stamp}.{signature}"


def is_admin(request):
    if not settings.HOSTED:
        return True
    if not settings.ADMIN_PASSWORD:
        return False
    value = request.cookies.get(COOKIE, "")
    try:
        stamp = int(value.split(".", 1)[0])
        age = time.time() - stamp
        return 0 <= age < 12 * 3600 and hmac.compare_digest(value, session_token(stamp))
    except (ValueError, TypeError):
        return False


async def access(request, call_next):
    if not settings.HOSTED:
        return await call_next(request)
    path = request.url.path
    admin = is_admin(request)
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if request.headers.get("sec-fetch-site") == "cross-site" or (
                origin and (urlsplit(origin).netloc != request.headers.get("host") or urlsplit(origin).scheme != request.url.scheme)):
            return JSONResponse({"detail": "다른 사이트에서 보낸 변경 요청은 허용하지 않습니다"}, status_code=403)
    if path == "/api/auth/login" and request.method == "POST":
        ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        recent = [t for t in _failures.get(ip, []) if now - t < 300]
        if len(recent) >= 5:
            return JSONResponse({"detail": "로그인 시도가 많습니다. 5분 뒤 다시 시도하세요"}, status_code=429)
        body = b""
        async for chunk in request.stream():
            body += chunk
            if len(body) > 4096:
                return JSONResponse({"detail": "로그인 요청이 너무 큽니다"}, status_code=413)
        try:
            password = json.loads(body).get("password", "")
        except (ValueError, AttributeError):
            password = ""
        if not isinstance(password, str) or not settings.ADMIN_PASSWORD or not secrets.compare_digest(password.encode(), settings.ADMIN_PASSWORD.encode()):
            if len(_failures) > 256:
                _failures.clear()
            _failures[ip] = recent + [now]
            return JSONResponse({"detail": "비밀번호를 확인하세요"}, status_code=401)
        _failures.pop(ip, None)
        response = JSONResponse({"admin": True})
        response.set_cookie(COOKIE, session_token(), max_age=12 * 3600, httponly=True, secure=True, samesite="strict", path="/")
        response.headers["Cache-Control"] = "no-store"
        return response
    if path == "/api/auth/logout" and request.method == "POST":
        response = JSONResponse({"admin": False})
        response.delete_cookie(COOKIE, path="/", secure=True, httponly=True, samesite="strict")
        return response
    public_api = path in ("/api/health", "/api/demo") and request.method in ("GET", "HEAD")
    if path.startswith("/api/") and not public_api and not admin:
        return JSONResponse({"detail": "관리자 로그인이 필요합니다"}, status_code=401)
    if not admin and (path in ("/requirements-source.md", "/devplan", "/catalog", "/learn") or path.startswith("/lecture")):
        return JSONResponse({"detail": "공개 예제에서 제공하지 않는 자료입니다"}, status_code=404)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    if path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response
