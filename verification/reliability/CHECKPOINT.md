# 기준점 절차 (상용 도구 재실행)

신뢰성 대응표(`table.md`)의 근거를 상용 도구로 다시 받는 절차다(SPEC 0019 4절). PR마다 하는 일이 아니다. 아래 시점에만 사람이 수동으로 실행하고, 결과 요약을 기준점 PR로 넣는다. 다음 사람이 같은 방법으로 근거를 갱신할 수 있게 순서를 고정한다.

## 1. 언제

| 시점 | 다시 받는 근거 |
| --- | --- |
| 새 DRC 규칙 묶음을 KLayout으로 옮겼을 때 | 새 규칙의 fixture Calibre 판정. 대응하는 규칙을 `ported`에서 `verified`로 올린다 |
| 도구 버전을 바꿨을 때(KLayout 0.30.x 등) | 모든 `verified` 규칙의 fixture 판정과 실제 칩 대조 |
| 제출 직전 최종 GDS | 최종 칩 GDS의 Calibre DRC·ANT·LVS와 같은 GDS의 오픈소스 판정 |

생성기(`scripts/asic/drc_cases.py`)를 고쳐 `verified` 규칙의 fixture 정의가 바뀐 경우도 그 fixture의 golden이 사라지므로 기준점이 필요하다.

## 2. 누가

- 실행: 프로젝트 담당자 승인 하에 사람이 수동으로 한다. 에이전트가 상용 도구를 스스로 실행하지 않는다.
- 학교 서버: 계정 주인의 동의와 상용 도구 실행 창구가 있을 때만 쓴다. 학교 서버는 우리 것이 아니고 계정도 빌린 것이다.
- 기준점 PR 승인: 도재겸 한 명이 근거를 확인한 뒤 PR 화면에서 우회 머지한다(ruleset의 `bypass_mode: pull_request`). 근거 파일·미검증 목록·규칙 상태를 바꾸는 PR은 `Baseline guard`가 일부러 실패하므로 우회 머지가 기록으로 남는다. 에이전트는 머지하지 않는다.
- RFC나 정답 모델도 함께 바꾸는 PR은 RFC 0002 PR01에 따라 팀장(김령교)의 승인을 받은 뒤 병합한다. golden만 추가·갱신하는 기준점 PR은 이 조항의 대상이 아니다.

## 3. 방법

1. **입력 묶음을 먼저 만든다.** 저장소의 커밋을 정하고, 그 커밋에서 입력을 만든다.
   - DRC fixture: `python scripts/asic/drc_selftest.py`로 fixture GDS와 `selftest.json`을 만들고 tarball로 묶는다.
   - 칩: 오픈소스 흐름 출력 GDS(`python scripts/run_asic.py --target chip`) 또는 최종 GDS, LVS source netlist.
2. **입력 해시를 기록한다.** tarball·GDS·netlist·키트 deck 파일의 sha256을 실행 전에 적는다. DRC deck은 `scripts/asic/drc_catalog.py`의 `SOURCE_SHA`(`6c01207311236d148dc183576fa8f5156e1a21d40a19609322c810fa919c4f0f`)와 같아야 한다.
3. **상용 도구를 무수정 deck으로 실행한다.** 키트 header에서 최상위 셀 이름만 바꾸고 규칙 본문은 고치지 않는다. DRC는 결과 수 제한을 풀고(`DRC MAXIMUM RESULTS ALL`), fixture는 GDS 하나마다 한 번씩 실행한다.
4. **결과를 저장소 밖으로 가져와 요약한다.** 서버에서 받은 원본 보고서·로그는 저장소 밖에 보관한다. 서버 이름·주소·계정·경로는 요약에 옮기지 않는다.
5. **golden을 만든다.** DRC fixture는 아래 5절의 `reliability.py import`로 만든다. 칩 결과는 `summary.json`과 `README.md`를 손으로 적되, 판정은 상용 보고서에 있는 값만 옮긴다.
6. **대응표를 고친다.** `table.json` 칸의 판정·범위·근거·갱신일을 고치고 `python scripts/asic/reliability.py render --table verification/reliability/table.json --out verification/reliability/table.md`로 `table.md`를 다시 만든다. 새 규칙이 검증됐으면 `verification/asic/drc-rules.json`의 `golden_compared`를 true로 바꾼다. 근거가 생긴 미검증 항목은 `unverified.json`에서 같은 PR로 뺀다.
7. **기준점 PR을 연다.** PR 본문에 실행 날짜·도구 버전·deck 해시·입력 해시와, `Baseline guard`가 실패하는 이유를 적는다.

golden은 상용 도구 출력이나 원본 규칙 문서에서만 만든다. 오픈소스 결과로 golden을 만들거나 덮어쓰지 않는다. 기존 golden 폴더는 고치지 않고, 새 실행은 새 날짜 폴더(`golden/<이름>-YYYYMMDD/`)에 넣는다.

## 4. 서버에 흔적을 남기지 않는 규칙

- 작업 폴더는 권한 700의 새 임시 폴더 하나만 쓰고, HOME도 그 안으로 지정해 도구 설정·캐시가 계정 홈에 쌓이지 않게 한다.
- 입력은 해시를 확인한 묶음만 올리고, 다른 사용자의 파일이나 설정을 읽거나 바꾸지 않는다.
- 끝나면 결과를 받은 뒤 임시 폴더 전체를 지우고, 접속에 쓴 SSH 키를 서버의 허용 목록과 내 쪽에서 모두 제거한다.
- 서버 식별 정보(호스트 이름·사용자·실행 경로)가 들어간 보고서 머리말은 보관용 사본에서 자리표시자로 바꾸고, 저장소에는 넣지 않는다.

## 5. golden 형식과 `reliability.py import`

### DRC fixture (`golden/drc-fixtures-YYYYMMDD/golden.json`)

- `meta`: `calibre_version`, `deck_sha256`, `fixture_tarball_sha256`, `generator_commit`, `run_date`, 그리고 fixture 해시 출처.
- `fixtures[]`: `gds`, `rule`(대상 규칙), `case_sha256`(fixture 정의 해시), `calibre`(`fired`/`clean`/`refused`), `target_count`, `other_rules`, `refused_reason`.
- 대조 기준은 대상 규칙의 발동 여부뿐이다. 마커 수와 대상 밖 규칙 발동은 기록만 한다. Calibre가 거부한 fixture는 사유가 붙은 제외로 보이며, 제외만 있는 규칙은 근거가 없는 것으로 본다.

입력은 두 개다. `calibre_counts.csv`는 fixture마다 한 줄(`gds,target_rule,target_rule_count,other_rules_fired,status,calibre_exit,run_ms`)이고, `other_rules_fired`는 `규칙:수;규칙:수` 형식이다. 거부된 fixture는 `calibre_exit`가 0이 아니며, 같은 실행의 로그(`results/<fixture>.calibre.log`)에서 첫 `ERROR:` 줄을 사유로 가져온다. `selftest.json`은 1단계에서 만든 KLayout 결과다.

```
python scripts/asic/reliability.py import --counts calibre_counts.csv --selftest selftest.json \
  --out verification/reliability/golden/drc-fixtures-YYYYMMDD/golden.json \
  --calibre-version v2023.4_17.10 \
  --deck-sha256 6c01207311236d148dc183576fa8f5156e1a21d40a19609322c810fa919c4f0f \
  --fixture-tarball-sha256 <입력 묶음 sha256> --generator-commit <fixture 생성 커밋> --run-date YYYY-MM-DD
```

- `--deck-sha256`이 `drc_catalog.SOURCE_SHA`와 다르면 거부한다.
- `--out`이 이미 있으면 덮어쓰지 않고 멈춘다.
- 만든 뒤 `python scripts/asic/reliability.py check --selftest selftest.json --golden verification/reliability/golden --out 새폴더`로 대조하고, 검증된 규칙이 모두 일치하는지 확인한다.

### 칩 결과 (`golden/chip-<이름>-YYYYMMDD/summary.json`)

실행일, 도구 버전, deck 해시와 무수정 여부, 입력 GDS·source netlist 해시, 설계별 DRC·ANT 결과 수와 LVS 판정(ports·nets·소자 수)을 적는다. 같은 GDS의 오픈소스 판정이 있으면 함께 적는다. 예시는 `golden/chip-openflow-20261128/`과 `golden/chip-v2-20261128/`이다. GDS 자체는 저장소에 넣지 않는다.

## 6. 첫 사례

2026-11-28 실행이 첫 기준점이다. Calibre `v2023.4_17.10`, 키트 deck 무수정으로 다음을 받았다.

- DRC fixture 427개: 425 일치, 2개 Calibre 거부(dbu). 입력 묶음 sha256 `a125b25350f984c46dde3d9c73f172bd085508ac540eddb35b86709e18a394d8`, 생성 커밋 `303bcb6` → `golden/drc-fixtures-20261128/`
- 오픈소스 흐름 코어·SOP28 칩의 DRC·ANT·LVS → `golden/chip-openflow-20261128/`
- v2 칩의 DRC·ANT·LVS → `golden/chip-v2-20261128/`
