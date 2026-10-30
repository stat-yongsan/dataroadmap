"""시험용 가짜 POST /v1/decisions — 공식 문서(26.10.31 확인)의 요청 · 응답 모양을 그대로 흉내 낸다. 표준 라이브러리만 쓴다.

경로 첫 조각이 시나리오다(/ok · /refusal …). 가짜 키가 아니면 assert 로 죽어, 진짜 키가 새는 것을 시험이 잡는다.
"""
import json
from http.server import BaseHTTPRequestHandler

FAKE_KEY = "test-fake-key"
FAKE_MODEL = "gpt-6-luna-fake-for-tests"


def answer(q, scen):
    if q["type"] == "predicate":
        return {"type": "predicate", "name": q["name"], "probability": 0.7}
    if q["type"] == "score":
        ps = [float(i == 1) for i in range(len(q["levels"]))]
        return {"type": "score", "name": q["name"], "score": 1.0, "confidence": 0.8,
                "probabilities": [{"value": i, "label": lv["label"], "probability": ps[i]} for i, lv in enumerate(q["levels"])]}
    vals = [c["value"] for c in q["choices"]]
    pr = {v: round(1 / len(vals), 6) for v in vals}
    pr[vals[0]] = round(pr[vals[0]] + 1 - sum(pr.values()), 6)
    a = {"type": "choice", "name": q["name"], "choice": vals[0], "confidence": 0.61,
         "probabilities": [{"value": v, "probability": pr[v]} for v in vals]}
    if scen == "offlist":
        a["choice"] = "X99"
    if scen == "noconf":
        a.pop("confidence")
    if scen == "partial":      # 0 인 선택지를 빼고 돌려주는 경우 — 문서가 보장하지 않으므로 앱은 거절해야 한다
        a["probabilities"] = a["probabilities"][:1]
        a["probabilities"][0]["probability"] = 1.0
    if scen == "badvalue":     # 문서와 다른 값 형태 — 파이썬 예외로 계획이 멈추지 않고 판단 실패로 남아야 한다
        a["probabilities"][0]["value"] = ["C03"]
    return a


class FakeDecisions(BaseHTTPRequestHandler):
    hits, bodies = {}, {}

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        scen = self.path.strip("/").split("/")[0]
        FakeDecisions.hits[scen] = FakeDecisions.hits.get(scen, 0) + 1
        FakeDecisions.bodies[scen] = body
        assert self.headers["Authorization"] == f"Bearer {FAKE_KEY}"
        if scen == "e401":
            return self._send(401, {"error": {"message": "Incorrect API key provided: sk-fake***"}})
        if scen == "e400":
            return self._send(400, {"error": {"message": "questions[0]: unsupported shape"}})
        if scen == "e500once" and FakeDecisions.hits[scen] == 1:
            return self._send(500, {"error": {"message": "server error"}})
        answers = [answer(q, scen) for q in body["questions"]]
        if scen == "refusal":
            answers = [{"type": "refusal", "name": a["name"]} if a["name"] == "next_step" else a for a in answers]
        return self._send(200, {"model": FAKE_MODEL, "answers": answers, "extra": 1, "usage": {
            "input_tokens": 100, "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
            "output_tokens": 10, "output_tokens_details": {"reasoning_tokens": 0}, "total_tokens": 110}})

    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)
