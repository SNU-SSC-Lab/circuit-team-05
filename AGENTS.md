# Circuit Team 05 작업 지침

## 시작 순서

1. README와 RFC 0002 `docs/rfcs/0002-collaboration.md`를 읽는다.
2. `docs/specs/README.md`에서 작업에 맞는 SPEC을 고른다. 새 기능이면 코드를 바꾸기 전에 SPEC을 작성한다.
3. SPEC에 연결된 RFC 조항과 이번 작업의 영향을 확인한다. 시작 훅이 알려 준 세션 ID로 `python scripts/policy.py review --session ID --spec SPEC경로 --summary "규약에 미치는 영향"`을 실행한다. 출력된 문서를 읽는다.
4. 보호 대상 파일을 수정한다. SPEC 범위를 벗어나거나 문서가 바뀌면 다시 확인한다.
5. 실제 실행한 검사 결과를 기록하고 What·Why·How로 PR을 작성한다. main에 직접 push하거나 임의 merge하지 않는다.

SPEC은 기획 의도·구현 계획이며 RFC는 규약이다. SPEC으로 규약을 말없이 변경하지 않는다. 기존 모듈 SPEC은 역작성 문서이므로 작성자의 원래 의도나 검증 완료로 단정하지 않는다.

## 문장과 시각화

쉬운 한국어와 실제 파일·모듈·신호 이름을 쓴다. 기술 용어는 필요할 때 뜻을 설명한다. 새로 만든 추상적인 표현, 불필요한 영어와 약어를 피한다. '정합성을 강화한다' 대신 '출력 중 IN_READY를 0으로 유지한다'처럼 조건과 동작을 적는다. 사실·제안·미확정 사항을 구분한다.

핵심 코드 변경은 짧은 수정 전후 코드나 diff로 설명한다. 블록·연결·순서 변경은 같은 이름을 사용한 변경 전후 흐름도를 제공하고 추가·삭제를 표시한다. 타이밍이 중요하면 에지표를 추가한다. 처음 역작성할 때는 현재 흐름만 그리며 없는 이전 설계를 만들지 않는다.

## 검사와 범위

`python scripts/policy.py check-docs`와 `python -m unittest discover -s tests/policy -v`를 실행한다. PR은 `python scripts/policy.py check-pr --body-file 본문파일 --base 기준브랜치`로 확인한다. 문서·훅 검사 통과를 RTL 시뮬레이션 통과로 기록하지 않는다.

훅을 비활성화하거나 --no-verify로 우회하지 않는다. 고장 난 정책 수정은 작업 브랜치에서 SPEC에 이유를 남겨 진행한다. 설치·지원 범위와 실제 에이전트 수동 확인은 `docs/hooks.md`를 참고한다. 훅 설정을 만드는 초기 PR은 RFC 0002의 초기 설치 예외를 따른다.
