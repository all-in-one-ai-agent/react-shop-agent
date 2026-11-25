import os
from pathlib import Path
from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.errors import GraphRecursionError
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

SHOPS = {"본관": {"삼각김밥": 0, "근처 매점": "학생회관"}, "학생회관": {"삼각김밥": 4}}
QUESTION = "본관 매점에 삼각김밥 있어? 품절이면 근처 매점을 확인해 줘."
EXPECTED = "학생회관"  # 위 재고표의 정답. 평가에만 쓰고 모델에는 주지 않는다.
SYSTEM = """삼각김밥 재고가 있으면 종료하고, 0개면 결과의 근처 매점을 확인한다.
이미 확인한 매점은 다시 조회하지 않는다. 미등록은 품절이 아니라 모름이다.
모르는 재고를 추측하지 않는다. 마지막 줄에는 구매 가능한 매점 이름만 쓴다.
살 곳이 없으면 품절, 재고를 알 수 없으면 모름이라고 쓴다."""


def find(shop):
    name = shop.strip().removesuffix("매점").strip()
    return {"매점": name, **SHOPS.get(name, {"상태": "미등록: 재고 모름"})}


@tool("lookup")
def act_lookup(shop: str) -> dict:
    """매점 재고 조회."""
    return find(shop)


@tool("lookup")
def react_lookup(shop: str, reason: str) -> dict:
    """매점 재고 조회. reason에는 직전 관찰을 반영한 짧은 조회 목적을 쓴다."""
    return find(shop)


def run(llm, method, memory=""):
    instructions = {
        "CoT": "도구 없이 주어진 정보로 짧은 풀이와 답을 쓴다.",
        "Act-only": "lookup을 사용한다. 행동 이유나 풀이 설명은 출력하지 않는다.",
        "ReAct": "lookup을 사용하고 reason에 짧은 행동 목적을 쓴다.",
    }
    tools = [] if method == "CoT" else [act_lookup if method == "Act-only" else react_lookup]
    model = llm.bind_tools(tools) if tools else llm
    builder = StateGraph(MessagesState)
    builder.add_node("chatbot", lambda state: {"messages": [model.invoke(state["messages"])]})
    builder.add_edge(START, "chatbot")
    if tools:
        builder.add_node("tools", ToolNode(tools))
        builder.add_conditional_edges("chatbot", tools_condition)
        builder.add_edge("tools", "chatbot")
    else:
        builder.set_finish_point("chatbot")
    messages = [("system", SYSTEM + "\n" + instructions[method] + "\n이전 반성 메모: " + memory),
                ("user", QUESTION)]
    trace, answer = [], ""
    try:
        for step in builder.compile().stream({"messages": messages}, stream_mode="updates",
                                             config={"recursion_limit": 9}):
            for update in step.values():
                for message in update["messages"]:
                    if message.type == "tool":
                        lines = ["Observation: " + message.content]
                    else:
                        lines = ["모델 텍스트: " + message.content] if message.content and message.tool_calls else []
                        for call in message.tool_calls:
                            args = call["args"]
                            if "reason" in args:
                                lines.append("Thought: " + args["reason"])
                            lines.append(f"Action: {call['name']}(shop={args.get('shop')!r})")
                        if not message.tool_calls:
                            answer = message.content
                            lines = ["Answer: " + answer]
                    for line in lines:
                        print(line)
                        trace.append(line)
    except GraphRecursionError:
        answer = ""
        trace.append("실행 한도 초과")
        print(trace[-1])
    return answer, "\n".join(trace)


def main(llm):
    for method in ("CoT", "Act-only", "ReAct", "Reflexion"):
        memory = ""
        for trial in range(2 if method == "Reflexion" else 1):
            print(f"\n[{method} / 시도 {trial + 1}]")
            answer, trace = run(llm, "ReAct" if method == "Reflexion" else method, memory)
            last_line = answer.strip().splitlines()[-1] if answer.strip() else ""
            ok = last_line.strip().removesuffix("매점").strip() == EXPECTED
            print("Evaluation:", "정답 일치" if ok else "불일치 또는 미완료")
            if ok or method != "Reflexion" or trial == 1:
                break
            memory = llm.invoke([
                ("system", "실패 궤적을 보고 다음 시도에서 바꿀 행동을 1~2문장 반성 메모로 쓴다."),
                ("user", QUESTION + "\n" + trace + "\n평가: 정답 불일치 또는 미완료"),
            ]).content
            print("Reflection → Memory:", memory)


if __name__ == "__main__":
    load_dotenv(Path(__file__).with_name(".env"))
    llm = ChatOpenAI(model="gpt-5.6-terra", temperature=0, max_tokens=1000,
                     api_key=os.environ["MONOROUTER_API_KEY"].strip(),
                     base_url="https://monogpt.kr/api/monorouter/v1", max_retries=0)
    main(llm)
