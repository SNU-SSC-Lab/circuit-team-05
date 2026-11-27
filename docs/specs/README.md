# SPEC 목록

규약은 `../rfcs/`에 두고 이 디렉터리는 기획 의도·구현·검증 계획을 기록한다.

- [0001-agent-hooks](0001-agent-hooks.md): 후킹 구현 계획
- [0002-ternary-decoder](0002-ternary-decoder.md): 기존 RTL 역작성
- [0003-ternary-term](0003-ternary-term.md): 기존 RTL 역작성
- [0004-adder12](0004-adder12.md): 기존 RTL 역작성
- [0005-accumulator-reg](0005-accumulator-reg.md): 기존 RTL 역작성
- [0006-illegal-flag-reg](0006-illegal-flag-reg.md): 기존 RTL 역작성
- [0007-weight-shift-reg](0007-weight-shift-reg.md): 기존 RTL 역작성
- [0008-nibble-rx](0008-nibble-rx.md): 기존 RTL 역작성
- [0009-result-tx](0009-result-tx.md): 기존 RTL 역작성
- [0010-dot8-controller](0010-dot8-controller.md): 기존 RTL 역작성
- [0011-v-ternary8-top](0011-v-ternary8-top.md): 기존 RTL 역작성

- [0012 RTL CI](0012-rtl-ci.md): PR 3의 문서·RTL 검증 CI 설계 초안
- [0013 MyChip 통합 검사 연결](0013-mychip-integration.md): 동아리 통합 저장소의 공통 계약 검사를 PR마다 실행. 2026-11-28 폐지(SPEC 0019)
- [0014 MyChip PDK 검사](0014-mychip-pdk-checks.md): 4차 PDK 합성·게이트 수준·타이밍과 mychip/ 산출물 검사를 PR마다 실행
- [0015 MyChip PDK 검사를 이 저장소로 옮기기](0015-own-pdk-checks.md): 같은 검사를 통합 저장소 없이 이 저장소의 scripts/로 실행, 게이트 수준은 팀 top 시험

- [0016 Magic DRC와 Netgen LVS](0016-magic-netgen.md): 도구 자체 시험 CI, 실제 회로 실행 준비와 상세 사용서
- [0017 RTL부터 GDS·검증·리포트](0017-rtl-to-gds.md): 비교 후 OpenROAD 구현·코어/제안 SOP28 생성·검사·리포트. 공정 전체 검증은 미완료

- [0018 공개 NSPL DRC 대조·시험 확장](0018-nspl-drc-rules.md): 원본 전체 목록, 규칙별 구현·시험, 담당자 요청문

- [0019 머지 게이트와 신뢰성 대응표](0019-merge-gate.md): main ruleset·필수 체크, Calibre 대응표·미검증 목록·기준점 절차, MyChip integration 폐지. 구현(GitHub 실행 기록 있음, main ruleset 전)

index.json은 검사 대상 파일과 확인한 규약의 버전을 기록한다. SHA256은 파일 내용으로 계산한 식별값이다. 사람이 읽는 설명은 각 SPEC의 RFC 확인 항목에 둔다.
