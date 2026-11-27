# SPEC 0013 MyChip 통합 검사 연결

> 폐지 메모(2026-11-28): `.github/workflows/integration.yml`(`MyChip integration`)을 삭제했다. 이 저장소는 2026-11-28 공개 전환으로 비공개 재사용 워크플로를 호출할 수 없어 PR 검사를 폐지했다. 칩 연결 검사는 circuit-integration 야간 작업이 이 저장소를 읽어 수행한다. 아래는 도입 당시 기록이다. 근거: [SPEC 0019](0019-merge-gate.md).

- 상태: 동아리 회로팀 다섯 저장소에 같은 연결을 PR로 제안한다. 팀이 승인해야 적용된다.
- 기준: `main` 위의 단일 PR. 기존 `RTL CI`(SPEC 0012)는 바꾸지 않는다.
- 관련 규약: RFC 0001 HW01~HW06(현재 회로 계약), RFC 0002 PR01·AUTO01.

## What

`.github/workflows/integration.yml`을 추가한다. PR과 `main` 커밋마다 동아리 통합 저장소 [SNU-SSC-Lab/circuit-integration](https://github.com/SNU-SSC-Lab/circuit-integration)의 검사를 이 저장소의 해당 커밋으로 실행한다. 다른 팀 칩은 그 저장소에 고정된(마지막으로 검사를 통과한) 커밋 기준이다.

검사 내용은 안내서(김태완, 2026-10-18) 공통 계약이다: top 포트 이름·방향·폭, Verilator lint, 핀 수준 시뮬레이션(매 에지 handshake 규칙, 출력 nibble 수·연속성, 32클록 응답 상한, 모든 위치의 reset, 안내서 golden 모델과 비트 단위 일치). 다섯 칩을 보드에서 이어 붙일 때 연결부가 맞는지 보는 것이 목적이다.

또 RTL 다음 단계 산출물을 둘 고정 폴더 `mychip/`의 뼈대를 추가한다(안내 `README.md`, 허용 파일 형식만 남기는 `.gitignore`, 빈 폴더 표시 `.gitkeep`). 합성 netlist·SDC·리포트는 `mychip/1-synth`·`mychip/constraints`에, 배치·배선 netlist·SPEF는 `mychip/2-pnr`에, DRC·LVS 리포트와 최종 GDS의 SHA-256은 `mychip/3-signoff`에 둔다. 통합 검사는 파일이 있는 단계만 검사하고(팀 netlist에 같은 시험기·4차 PDK 타이밍, 사인오프 리포트 판정), 없는 단계는 실패로 치지 않는다. 통합 저장소의 규칙은 `contract/flow.toml`이다.

RTL·테스트·기존 workflow는 바꾸지 않는다.

## Why

칩 다섯 개는 팀마다 따로 만들지만, 실리콘을 받은 뒤 같은 시험기·보드에 함께 연결한다. 팀끼리 일일이 맞추지 않아도 연결부가 어긋나지 않게 하려면, 같은 계약을 같은 테스트벤치로 매 변경마다 확인해야 한다. 이 저장소의 RTL CI는 팀 RFC 기준으로 깊게 검사하고, 통합 검사는 다섯 칩 공통 기준으로 넓게 검사한다. 두 검사는 서로를 대신하지 않는다.

## How

workflow 하나가 통합 저장소의 재사용 workflow(`checks.yml`)를 호출한다. 다른 팀의 비공개 저장소는 저장소마다 둔 읽기 전용 deploy key(Actions secret `CIRCUIT_*_KEY`, 이미 설정됨)로만 읽는다. 이 저장소에서 쓰기 권한은 요청하지 않는다(`contents: read`).

현재 `main`(a0120cc)은 통합 저장소 첫 실행에서 포트·lint·시뮬레이션을 모두 통과했다. RFC 0001과 통합 계약의 차이는 발견되지 않았다. 통합 검사의 자체 검사(복사본에 버그를 심어 반드시 잡는지)에서도 이 저장소 RTL에 심은 `illegal` 누적 누락, 결과 11비트 축소가 모두 검출됐다.

흐름 변경: 없음
시각화 생략 이유: RTL 블록·순서·연결과 기존 CI 흐름을 바꾸지 않고, PR에 체크 하나와 빈 산출물 폴더가 추가된다.

## RFC 확인

RFC 0001의 회로 계약(입력 10바이트, 출력 4 nibble, 12비트 부호·오류 플래그, 응답 상한, reset)은 통합 계약 `contract/interface.toml`과 같다. 이 PR은 RFC 0001을 바꾸지 않는다. RFC 0002 PR01에 따라 별도 브랜치·PR로 제안하고, AUTO01에 따라 자동 검사 결과와 사람의 판단을 구분한다. 통합 검사 통과를 물리 검증이나 제작 가능 판정으로 표시하지 않는다.
