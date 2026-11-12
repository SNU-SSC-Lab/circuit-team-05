# 에이전트 훅과 공통 검사 사용 방법

Python 3.10 이상과 Git이 필요하다. 추가 Python 패키지는 없다. Windows에서는 Git for Windows의 Git Bash와 PowerShell을 사용한다. Linux·macOS에서는 python 명령이 Python 3을 실행해야 한다.

## 설치

```text
python --version
python scripts/install_hooks.py
python scripts/policy.py check-docs
python -m unittest discover -s tests/policy -v
```

설치 명령은 이 저장소의 core.hooksPath를 .githooks로 설정한다. 다른 경로가 이미 있으면 덮어쓰지 않는다. 전역 Git·에이전트 설정과 신뢰 승인은 변경하지 않는다. Git 훅 파일은 clone만으로 활성화되지 않으므로 팀원마다 설치한다.

- Claude Code: 저장소 루트에서 시작하고 `/hooks`에서 프로젝트 SessionStart·PreToolUse를 확인한다. JSON 설정은 `.claude/settings.json`이다.
- Codex: 프로젝트를 신뢰한 뒤 `/hooks` 또는 앱의 Review hooks에서 정의를 읽고 신뢰한다. `.codex/hooks.json`을 사용한다. 새로 바뀐 훅은 다시 검토해야 할 수 있다. 현재 세션이 자동으로 새 훅을 적용한다고 가정하지 않는다.

## 작업 순서

시작 메시지의 세션 ID를 사용한다. 작업에 해당하는 SPEC은 `docs/specs/README.md`에서 선택한다.

```text
python scripts/policy.py review --session 세션ID --spec docs/specs/0001-agent-hooks.md --summary "후킹 동작을 바꾸며 RFC 0002의 사전 확인과 PR 검사 규칙을 유지한다"
```

명령이 출력한 SPEC과 RFC를 읽고 작업한다. 기록은 `.git/ssc-policy/` 아래에만 저장하며 커밋하지 않는다. 새 세션이거나 확인한 문서·목록이 바뀌면 다시 확인한다. 여러 SPEC이 필요하면 --spec을 반복한다. 역작성 SPEC을 사용하려면 관련 규약 버전과 현재 작업의 영향을 검토한다.

`index.json`은 SPEC 대상 경로와 RFC 내용의 SHA256을 기록한다. 줄바꿈은 LF로 맞춰 계산하므로 Windows의 CRLF checkout에서도 같은 규약 버전을 사용한다. RFC를 바꿨다면 관련 SPEC의 설명을 검토한 후 변경에 사용하는 항목의 SHA256도 갱신한다. 이전 작업 SPEC은 역사적 참조를 유지할 수 있지만 현재 코드 변경에 선택하면 최신 규약과 다시 대조해야 한다. 단순히 해시만 바꾸는 것은 규약 확인을 대신하지 않는다.

## PR 검사와 다음 CI 연결

PR 본문은 `.github/pull_request_template.md`를 사용한다. How에 `docs/specs/0001-agent-hooks.md`처럼 실제 SPEC 경로를 적는다. 코드 변경이면 `흐름 변경: 있음` 또는 `흐름 변경: 없음`을 적는다. 있음이면 SPEC에 변경 전후 그림 두 개와 핵심 diff가 있어야 한다. 없음이면 `시각화 생략 이유:`를 적는다. 선언이 실제 코드와 맞는지는 리뷰 대상이다.

```text
python scripts/policy.py check-pr --body-file PR본문파일 --base origin/기준브랜치
```

검사기는 base와 HEAD의 공통 조상 이후 변경을 확인한다. 연속 PR 2의 base는 PR 1 작업 브랜치다. 앞 PR이 병합되면 기준과 필요한 커밋 이력을 정리한다. `gh pr create`에는 --base를 명시한다. `gh pr edit`의 본문 수정은 전체 변경 파일 검사에 필요한 base를 위 check-pr 명령으로 별도 제공한다.

다음 CI PR은 이 명령에 실제 PR 본문·base·head를 전달하고 결과를 상태 검사로 표시한다. 이번 PR에는 Workflow를 추가하지 않는다. 서버에서 PR body를 셸 명령으로 보간하거나 PR의 임의 코드를 권한 있는 이벤트에서 실행하지 않도록 별도 설계한다.

## 지원 범위

| 경로 | 이번 구현 |
| --- | --- |
| Edit·Write·MultiEdit, Codex apply_patch | 보호 경로 수정 전 SPEC 범위·확인 기록 검사 |
| Bash·PowerShell·exec_command | 명확한 읽기 명령은 허용, 그 외 확인 기록 요구 |
| gh pr create·edit의 본문 | What·Why·How 및 SPEC 검사. create는 명시한 base로 변경 범위도 검사 |
| GitHub 연결 도구의 PR body | 같은 본문 검사. base가 제공되면 변경 범위도 검사 |
| GitHub 연결 도구의 원격 코드·ref 쓰기 | 로컬 브랜치와 PR 사용을 안내하고 차단 |
| 실제 Git push | stdin의 모든 ref를 검사해 원격 main 생성·갱신·삭제 차단 |

임의 셸 프로그램이 쓰는 파일을 실행 전에 완전하게 알 수는 없다. 셸 확인 기록만으로 실제 변경 파일 범위를 보장하지 않으며 PR 검사에서 다시 대조한다. 임의 HTTP 도구·직접 편집기·훅을 끈 세션까지 막는 보안 경계가 아니다. GitHub 브랜치 보호는 별도이며 현재 비공개 저장소의 요금제 제한도 따로 확인해야 한다.

## 시험 증거와 수동 확인

자동 시험은 두 에이전트 형식의 실제 JSON을 Python 진입점과 설정의 셸 명령에 전달한다. Git 검사는 임시 로컬 bare 원격으로 실제 push를 수행한다. 모델 호출·원격 main push는 하지 않는다.

실제 에이전트에서 다음을 수동 확인하기 전까지 '모델 세션에서 활성화 완료'라고 기록하지 않는다.

1. 프로젝트 훅이 목록에 있고 신뢰 상태가 유효한지 확인한다.
2. 임시 작업 파일을 대상으로 확인 없는 보호 경로 편집이 실행 전에 거절되는지 확인한다.
3. 관련 SPEC 확인 후 같은 편집이 허용되는지 확인한다.
4. RFC를 수정하면 재확인이 필요한지 확인한다.

이는 내용 이해를 증명하지 않는다. 문장 가독성·기획 타당성·흐름도와 코드의 일치는 사람이 검토한다.

## 공식 참고 문서

- [Codex Hooks](https://learn.chatgpt.com/docs/hooks)
- [Claude Code Hooks](https://code.claude.com/docs/en/hooks)

설정 형식과 도구 지원은 버전에 따라 확인한다. 이 작업 환경의 설치 버전은 Codex CLI 0.167.2, Claude Code 2.1.319다.
