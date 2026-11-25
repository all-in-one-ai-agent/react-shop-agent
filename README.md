# ReAct 실습 · 매점 재고 조회 에이전트

“본관 매점에 삼각김밥 있어? 품절이면 근처 매점을 확인해 줘.”라는 질문을 LangGraph로 실행합니다. 예제 재고는 본관 0개, 학생회관 4개이며, 같은 질문에 CoT·Act-only·ReAct·Reflexion이 어떻게 응답하는지 비교합니다.

## 파일

| 파일 | 내용 |
|---|---|
| `compare_shop.py` | 매점 조회 도구, 모델–도구 호출 루프, 정답 평가 및 Reflexion 재시도 |
| `requirements.txt`, `.env.example` | Python 의존성과 수업용 API 키 설정 예시 |
| [logs/notion-run.txt](logs/notion-run.txt) | 팀 Notion에 기록된 실제 실행 출력 |
| [verification/verify_offline.py](verification/verify_offline.py) | 실제 API 키 없이 도구 호출과 재시도 분기를 확인하는 스크립트 |

## 설치와 실행

Python 3.12로 확인했습니다. macOS와 Linux에서는 다음 명령으로 환경을 준비합니다. Windows PowerShell에서는 `python3` 대신 `py -3.12`를 사용하고 `source` 줄 대신 `.\.venv\Scripts\Activate.ps1`을 실행하고 `cp` 대신 `Copy-Item`을 사용합니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

`.env`의 `MONOROUTER_API_KEY` 값을 본인에게 발급된 MonoRouter API 키로 바꾼 뒤 실행합니다. 실습은 MonoRouter의 수업용 엔드포인트를 통해 `gpt-5.6-terra`를 호출합니다. 키는 로컬 `.env`에만 보관합니다.

```bash
python compare_shop.py
```

API 키 없이 실행 흐름을 확인하려면 다음 명령을 사용합니다. 이 스크립트는 모델 응답을 모의로 지정하고 LangGraph의 도구 호출, 첫 시도 성공 시 종료, 실패 후 반성 메모를 넣은 재시도, 반복 한도와 채점을 점검합니다.

```bash
python verification/verify_offline.py
```

## 실행 결과

팀 Notion에서 2026-11-25에 확인한 실행 기록입니다.

| 방식 | 동작 | Notion에 기록된 응답 |
|---|---|---|
| CoT | 재고 정보나 조회 도구 없이 짧은 풀이 요청 | 모름 |
| Act-only | `lookup(shop)`으로 조회하고 관찰 결과에 따라 다음 매점 조회 | 학생회관, 정답 일치 |
| ReAct | `lookup(shop, reason)`에 조회 목적을 넣고 관찰 결과에 따라 다음 매점 조회 | 학생회관 매점, 정답 일치 |
| Reflexion | ReAct의 첫 시도가 틀리면 반성 메모를 만들어 한 번 더 시도 | 학생회관 매점, 첫 시도 정답 일치 |

출력의 `Thought`는 도구에 전달한 짧은 조회 목적입니다. `Action`은 조회 호출, `Observation`은 재고표에서 받은 값입니다. 평가는 답변 마지막 줄의 공백과 끝의 “매점”을 정리한 뒤 정답 매점 이름과 비교합니다. 기록된 Reflexion 실행은 첫 시도에 맞혀 반성 단계가 생략됐습니다. 반성 후 재시도는 위 모의 검증으로 확인했습니다. 모델 응답과 조회 목적은 새로 실행할 때 달라질 수 있습니다.

이 실행은 조회 도구에 접근할 수 있는지와 관찰 이후 행동이 어떻게 바뀌는지 보여줍니다. CoT에는 재고 정보가 주어지지 않고 Reflexion에는 실패 시 추가 시도가 주어지므로, 한 사례의 결과로 네 방식의 정확도를 비교하기는 어렵습니다.

## 참고 자료

- [ReAct · Yao 외, ICLR 2023](https://arxiv.org/abs/2210.03629)
- [Chain-of-Thought Prompting · Wei 외, NeurIPS 2022](https://arxiv.org/abs/2201.11903)
- [Reflexion · Shinn 외, NeurIPS 2023](https://arxiv.org/abs/2303.11366)
