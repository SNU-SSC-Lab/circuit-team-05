# 기준점 절차 (상용 도구 재실행)

신뢰성 대응표(`table.md`)의 근거를 상용 도구로 다시 받는 절차다(SPEC 0019 4절). PR마다 하는 일이 아니다. 아래 시점에만 사람이 수동으로 실행하고, 결과 요약을 기준점 PR로 넣는다. 다음 사람이 같은 방법으로 근거를 갱신할 수 있게 순서를 고정한다.

## 1. 언제

| 시점 | 다시 받는 근거 |
| --- | --- |
| 새 DRC 규칙 묶음을 KLayout으로 옮겼을 때 | 새 규칙의 fixture Calibre 판정. 대응하는 규칙을 `ported`에서 `verified`로 올린다 |
| 도구 버전을 바꿨을 때(KLayout 0.30.x 등) | 모든 `verified` 규칙의 fixture 판정, 변형본 판정과 실제 칩 대조. 변형본 golden의 형상 해시는 KLayout 0.28.16으로 계산했으므로(`meta.klayout_version`) 버전이 바뀌어 해시가 달라지면 `check-mutations`가 실패한다 |
| 제출 직전 최종 GDS | 최종 칩 GDS의 Calibre DRC·ANT·LVS와 같은 GDS의 오픈소스 판정 |

생성기(`scripts/asic/drc_cases.py`)를 고쳐 `verified` 규칙의 fixture 정의가 바뀐 경우도 그 fixture의 golden이 사라지므로 기준점이 필요하다. 변형본 생성기(`scripts/asic/mutate.py`, `scripts/asic/mutate_v2.py`)를 고쳐 같은 seed에서 다른 형상이 나오는 경우도 같다.

## 2. 누가

- 실행: 프로젝트 담당자 승인 하에 사람이 수동으로 한다. 에이전트가 상용 도구를 스스로 실행하지 않는다.
- 학교 서버: 계정 주인의 동의와 상용 도구 실행 창구가 있을 때만 쓴다. 학교 서버는 우리 것이 아니고 계정도 빌린 것이다.
- 기준점 PR 승인: 도재겸 한 명이 근거를 확인한 뒤 PR 화면에서 우회 머지한다(ruleset의 `bypass_mode: pull_request`). 근거 파일·미검증 목록·규칙 상태를 바꾸는 PR은 필수 체크 `baseline-guard`가 일부러 실패하므로 우회 머지가 기록으로 남는다. 같은 PR에는 `baseline-label` job이 `baseline-change` 라벨을 붙이고, `.github/CODEOWNERS`가 도재겸에게 리뷰를 요청한다(리뷰 요청일 뿐 필수 승인이 아니다). 우회 머지는 `baseline-guard`만 실패하고 나머지 필수 체크가 모두 통과한 PR에만 한다. 에이전트는 머지하지 않는다.
- RFC나 정답 모델도 함께 바꾸는 PR은 RFC 0002 PR01에 따라 팀장(김령교)의 승인을 받은 뒤 병합한다. 기준 파일(golden·대응표·미검증 목록·규칙 상태)만 바꾸는 기준점 PR은 이 조항의 대상이 아니다. 기준 파일과 RFC나 정답 모델을 함께 바꾸는 PR은 팀장(김령교)의 승인과 도재겸의 근거 확인·PR 우회 머지가 모두 필요하다(SPEC 0019).

## 3. 방법

1. **입력 묶음을 먼저 만든다.** 저장소의 커밋을 정하고, 그 커밋에서 입력을 만든다.
   - DRC fixture: `python scripts/asic/drc_selftest.py`로 fixture GDS와 `selftest.json`을 만들고 tarball로 묶는다.
   - 칩: 오픈소스 흐름 출력 GDS(`python scripts/run_asic.py --target chip`) 또는 최종 GDS, LVS source netlist.
2. **입력 해시를 기록한다.** tarball·GDS·netlist·키트 deck 파일의 sha256을 실행 전에 적는다. DRC deck은 `scripts/asic/drc_catalog.py`의 `SOURCE_SHA`(`6c01207311236d148dc183576fa8f5156e1a21d40a19609322c810fa919c4f0f`)와 같아야 한다.
3. **상용 도구를 무수정 deck으로 실행한다.** 키트 header에서 최상위 셀 이름만 바꾸고 규칙 본문은 고치지 않는다. DRC는 결과 수 제한을 풀고(`DRC MAXIMUM RESULTS ALL`), fixture는 GDS 하나마다 한 번씩 실행한다.
4. **결과를 저장소 밖으로 가져와 요약한다.** 서버에서 받은 원본 보고서·로그는 저장소 밖에 보관한다. 서버 이름·주소·계정·경로는 요약에 옮기지 않는다.
5. **golden을 만든다.** DRC fixture는 아래 5절의 `reliability.py import`로 만든다. 칩 결과는 `summary.json`과 `README.md`를 손으로 적되, 판정은 상용 보고서에 있는 값만 옮긴다.
6. **대응표를 고친다.** `table.json` 칸의 판정·범위·근거·갱신일을 고치고 `python scripts/asic/reliability.py render --table verification/reliability/table.json --out verification/reliability/table.md`로 `table.md`를 다시 만든다. 새 규칙이 검증됐으면 `verification/asic/drc-rules.json`의 `golden_compared`를 true로 바꾼다. 근거가 생긴 미검증 항목은 `unverified.json`에서 같은 PR로 뺀다.
7. **기준점 PR을 연다.** PR 본문에 실행 날짜·도구 버전·deck 해시·입력 해시와, `baseline-guard`가 실패하는 이유를 적는다.

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

### DRC 변형본 (`golden/drc-mutations-YYYYMMDD/golden.json`)

키트 셀(과 선택적으로 코어 GDS 창)의 도형 하나를 고친 GDS를 Calibre로 하나씩 검사한 결과다. 형상 해시(`geometry_sha256`)로 묶는다. 입력은 Calibre 발동 규칙 표(`gds,rules_fired,calibre_exit,run_ms,calibre_error`), 변형본 `manifest.json`, `mutate.py hash`로 낸 형상 해시다.

```
python scripts/asic/mutate.py hash --gds-dir 입력묶음폴더 --out geometry.json
python scripts/asic/reliability.py import-mutations --counts counts.csv --manifest 입력묶음폴더/manifest.json \
  --geometry geometry.json --out verification/reliability/golden/drc-mutations-YYYYMMDD/golden.json \
  --generator scripts/asic/mutate_v2.py --calibre-version v2023.4_17.10 \
  --deck-sha256 6c01207311236d148dc183576fa8f5156e1a21d40a19609322c810fa919c4f0f \
  --corpus-tarball-sha256 <입력 묶음 sha256> --run-date YYYY-MM-DD --klayout-version <형상 해시를 계산한 KLayout>
```

- 저장소에 없는 입력(우리 흐름의 코어 GDS)에서 만든 변형본은 `--checkpoint-only-source 파일이름`으로 표시한다. CI는 이것을 다시 만들지 않고 `not_regenerated`로 세며, 기준점에서 같은 파일을 `check-mutations --core-gds`로 주면 비교한다.
- 만든 뒤 `python scripts/asic/reliability.py check-mutations --kit 키트폴더 --out 새폴더`로 모든 변형본 golden을 대조한다. 예시와 필드 설명은 `golden/drc-mutations-20261128/README.md`(1차, `mutate.py`)와 `golden/drc-mutations-20261128b/README.md`(2차, `mutate_v2.py`)에 있다.

### 칩 결과 (`golden/chip-<이름>-YYYYMMDD/summary.json`)

실행일, 도구 버전, deck 해시와 무수정 여부, 입력 GDS·source netlist 해시, 설계별 DRC·ANT 결과 수와 LVS 판정(ports·nets·소자 수)을 적는다. 같은 GDS의 오픈소스 판정이 있으면 함께 적는다. 예시는 `golden/chip-openflow-20261128/`과 `golden/chip-v2-20261128/`이다. GDS 자체는 저장소에 넣지 않는다.

### 미구현 규칙 fixture (`golden/<이름>-YYYYMMDD/golden.json`, `meta.pending` = true)

KLayout 구현이 없는 규칙의 fixture golden이다. 항목 형식은 DRC fixture golden과 같고, `group`(묶음)과 `deck`(DRC/ANT)이 더 있다. `reliability.py check`는 이 파일을 읽지 않고, `python scripts/asic/reliability.py check-pending`이 fixture 정의(`scripts/asic/drc_cases_pending.py`)와 1:1인지와, Calibre가 판정한 fixture에서 정의의 `fail`이 Calibre 판정과 같은지만 확인한다. fixture 정의는 생성한 파일을 그대로 옮겨 `case_sha256`이 Calibre가 읽은 GDS의 manifest 값과 같게 한다. 가설(`fail`)이 Calibre와 다르면 정의를 Calibre 판정으로 고치고, golden 항목에 Calibre가 읽은 정의의 해시를 `run_case_sha256`으로 남긴다. Calibre가 입력을 거부한 fixture는 정의를 고치지 않고 `refused`와 사유로 남긴다(사유가 붙은 제외, 첫 묶음의 0169·0170과 같음). `raises`는 우리 GDS 작성기나 KLayout이 오류를 내는 경우에만 쓴다.

규칙을 KLayout으로 옮기면 그 fixture를 `scripts/asic/drc_cases.py`로 옮기고(같은 `case_sha256`), 규칙을 `drc_cases_pending.py`의 `MOVED_RULES`에 넣는다. golden 항목은 pending 파일을 고치지 않고 새 fixture golden 폴더로 그대로 복사한다(`meta.moved_from`·`moved_from_sha256`). `check-pending`은 pending golden에 남은 항목을 `moved`로 세고, 같은 해시·규칙·Calibre 판정이 fixture golden에 있는지 확인한다. 첫 사례는 키트 ANT deck 12개 검사(102개, `golden/ant-fixtures-20261128/`, SPEC 0020)다.

## 6. 첫 사례

2026-11-28 실행이 첫 기준점이다. Calibre `v2023.4_17.10`, 키트 deck 무수정으로 다음을 받았다.

- DRC fixture 427개(첫 묶음 기록): 425 일치, 2개 Calibre 거부(dbu). 지금 숫자는 아래 둘러싸기 묶음과 합친 451개 중 449개 일치, 2개 제외. 입력 묶음 sha256 `a125b25350f984c46dde3d9c73f172bd085508ac540eddb35b86709e18a394d8`, 생성 커밋 `303bcb6` → `golden/drc-fixtures-20261128/`
- 둘러싸기 경계 fixture 24개(`0427`~`0450`): 24개 모두 정의의 기대값과 같음 → `golden/drc-fixtures-20261128b/`. 두 묶음을 합쳐 fixture 451개 중 449개 일치, 2개 제외
- 키트 셀 변형본 695개(1차, `mutate.py`): 81개 Calibre 거부(자기 교차) → `golden/drc-mutations-20261128/`
- 키트 셀 604개 + 코어 창 196개 변형본 800개(2차, `mutate_v2.py`): Calibre 거부 0 → `golden/drc-mutations-20261128b/`
- 오픈소스 흐름 코어·SOP28 칩의 DRC·ANT·LVS → `golden/chip-openflow-20261128/`
- v2 칩의 DRC·ANT·LVS → `golden/chip-v2-20261128/`
- 2차(같은 날): 아직 KLayout에 없는 113개 규칙·전역 플래그·ANT deck 12개 검사의 fixture 857개 → `golden/drc-unported-20261128/`(ANT 102개는 KLayout 이식 뒤 `golden/ant-fixtures-20261128/`로 옮김), 코어·SOP28 칩·표준셀 34종·GPIO 9종 LVS → `golden/lvs-20261128/`, OpenSTA ↔ Tempus 타이밍 → `golden/sta-20261128/`, ngspice ↔ Spectre → `golden/spice-20261128/`, Calibre xRC 기준 자료(파일은 저장소 밖) → `golden/pex-reference-20261128/`

## 7. 2026-11-28 실행에서 배운 절차

### 서버에 파일을 남기지 않기

- 실행 스크립트 첫머리에 `umask 077`과 `unset HISTFILE`을 둔다. fixture GDS와 deck 링크는 실행 폴더에 잠깐 두고 실행이 끝나면 바로 지운다.
- 결과를 받기 전에 서버 쪽에서 보고서·로그 머리말의 서버 식별 정보를 자리표시자(`<host>`, `<user>`, `<rundir>`, `<work>`, `<calibre>`)로 바꾼다. 압축된 로그(`.gz`) 안도 바꾼다.
- 서버에 python이 없으면 측정·집계는 결과를 받은 뒤 로컬에서 같은 스크립트로 한다(2차 K2).
- 끝나면 임시 폴더 전체를 지우고, 지웠다는 사실을 결과 README에 적는다.

### 결과 정리 방식

- 묶음마다 `REQUEST.md`(정확한 명령·header 변경), `SHA256SUMS`(입력), 결과 README(도구 판, deck·입력 sha256, 실제 명령, 지시서와 다르게 한 점)를 둔다.
- 결과 CSV는 열을 고정한다(`gds,target_rule,target_rule_count,other_rules_fired,status,calibre_exit,run_ms`). `status`는 실행 상태일 뿐이고, 의도와의 비교는 로컬에서 한다.
- 저장소에는 판정에 필요한 요약(`golden.json` 또는 `summary.json` + `README.md`)과 해시만 넣는다. DSPF·SPEF·svdb·GDS·원본 보고서는 저장소 밖 근거 묶음에 두고, README에는 실행일과 sha256으로 가리킨다. 로컬 컴퓨터 경로도 적지 않는다.
- 두 도구를 비교할 때는 입력을 같게 만든 방법을 적는다. 이름 형식 차이(SPEF의 인스턴스 `X` 접두어, 넷 이름 대소문자)를 로컬에서 고쳤다면 고친 규칙과 개수, 고친 파일의 sha256을 남긴다. 한 도구만 읽는 제약 문법(OpenSTA 전용 `delete_from_list`)은 다른 도구용 사본을 만들고 정확한 diff를 적는다.

### deck 수정이 불가피할 때

키트 deck은 고치지 않는 것이 원칙이다. 그래도 그대로는 실행이 안 되면(2차 C5: PEX deck이 batch xRC를 거부) 다음 순서를 지킨다.

1. 먼저 header만으로 해결되는지 시험하고, 안 되면 그 오류 문구를 기록한다.
2. 키트 deck은 그대로 두고 실행 폴더에 사본을 만든다.
3. 바꿀 줄의 정확한 diff를 실행 전에 파일로 적어 둔다(`expected_*.diff`). 실행 스크립트는 사본과 키트 deck의 실제 diff가 이 파일과 한 글자라도 다르면 멈춘다.
4. 실행 폴더마다 실제 diff와 사본의 sha256을 남기고, golden README에 diff 전문을 적는다(`golden/pex-reference-20261128/README.md`).
5. header에 줄을 더한 경우도 같은 방식으로 기록한다(GPIO 단독 LVS의 `VIRTUAL CONNECT NAME "VDD" "VSS"`, `golden/lvs-20261128/README.md`).
