"""모델 응답만 HTTP mock으로 지정. 실제 SDK/그래프/도구 연결 검증."""
import contextlib
import importlib.util
import io
import json
import platform
from unittest.mock import patch
from pathlib import Path
import httpx
from langchain_openai import ChatOpenAI

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("compact", root / "compare_shop.py")
shop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shop)
queue, requests = [], []


def answer(text):
    return {"role": "assistant", "content": text}


def lookup(name, reason=None):
    args = {"shop": name}
    if reason:
        args["reason"] = reason
    return {"role": "assistant", "content": None, "tool_calls": [
        {"id": "call_" + name, "type": "function", "function": {
            "name": "lookup", "arguments": json.dumps(args, ensure_ascii=False)}}]}


def respond(request):
    requests.append(json.loads(request.content))
    message = queue.pop(0)
    return httpx.Response(200, json={"id": "offline", "object": "chat.completion", "created": 0,
        "model": "http-mock", "choices": [{"index": 0, "message": message,
        "finish_reason": "tool_calls" if "tool_calls" in message else "stop"}]})


def prepare(failure=False):
    queue[:] = [answer("현재 재고를 알 수 없다.\n모름"), lookup("본관"), lookup("학생회관"), answer("학생회관"),
                lookup("본관", "본관 재고 확인"), lookup("학생회관", "본관 품절이므로 근처 확인"), answer("학생회관")]
    queue.extend([lookup("본관", "본관 재고 확인")])
    if failure:
        queue.extend([answer("품절"), answer("본관만 확인하고 멈췄다. 근처 매점도 확인한다.")])
    queue.extend([lookup("학생회관", "근처 매점 확인"), answer("학생회관")])
    if failure:
        # 재시도는 본관부터 새 궤적. 반성 문장만 이전 시도에서 전달된다.
        queue[-2:-2] = [lookup("본관", "이전 반성 메모를 참고해 다시 확인")]
    requests.clear()


print(f"Python {platform.python_version()}")
print("외부 API 호출 없음. 아래 모델 판단·반성 문장은 분기 검증용 모의 응답이다.")
with httpx.Client(transport=httpx.MockTransport(respond)) as client:
    llm = ChatOpenAI(model="http-mock", api_key="offline-placeholder", max_retries=0,
                     base_url="https://local.invalid/v1", http_client=client)
    for failure in (False, True):
        prepare(failure)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            shop.main(llm)
        text = out.getvalue()
        assert not queue
        assert ("[Reflexion / 시도 2]" in text) == failure
        assert text.count("Reflection → Memory:") == int(failure)
        act = text.split("[Act-only / 시도 1]")[1].split("[ReAct / 시도 1]")[0]
        assert "Thought:" not in act and act.count("Action:") == 2
        assert '"삼각김밥": 4' in act or '"삼각김밥":4' in act
        assert "tools" not in requests[0]
        for req in requests:
            if req.get("tools"):
                params = req["tools"][0]["function"]["parameters"]["properties"]
                is_act = "행동 이유나 풀이 설명은 출력하지 않는다" in req["messages"][0]["content"]
                assert ("reason" in params) != is_act
        if failure:
            retry = next(req for req in requests if "이전 반성 메모: 본관만" in req["messages"][0]["content"])
            assert len(retry["messages"]) == 2
            assert "학생회관" not in retry["messages"][0]["content"]
            print(text)
        print("PASS", "실패→평가→반성 메모를 넣은 새 시도" if failure else "네 방식·도구 schema·성공 시 즉시 종료")
    queue[:] = [lookup("본관", "반복") for _ in range(20)]
    with contextlib.redirect_stdout(io.StringIO()):
        result, trace = shop.run(llm, "ReAct")
    assert result == "" and "실행 한도 초과" in trace and "Observation:" in trace
    print("PASS 반복 한도·실패 궤적 보존")
for final, correct in (("학생회관", True), ("학생회관 매점", True),
                       ("설명 문장\n\n학생회관매점  ", True), ("본관 매점", False),
                       ("품절", False), ("모름", False), ("", False)):
    out = io.StringIO()
    with patch.object(shop, "run", side_effect=lambda llm, method, memory: (final if method == "CoT" else "학생회관", "")), contextlib.redirect_stdout(out):
        shop.main(None)
    cot = out.getvalue().split("[Act-only")[0]
    assert ("Evaluation: 정답 일치" in cot) == correct
print("PASS 실제 채점 경로: 매점 접미사/공백/다중 줄 허용, 오답·모름·빈 답 거부")
print("ALL PASS — 실제 LLM 성능 결과가 아님")
