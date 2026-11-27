# 아직 KLayout에 없는 DRC·antenna 규칙의 Calibre golden (2026-11-28)

KLayout으로 옮기지 않은 DRC 규칙 113개, 전역 입력 플래그(NONSIMPLE·ACUTE), 키트 ANT deck의 12개 검사(RULECHECK)마다 시험 도형(fixture)을 만들어 Calibre로 한 번씩 검사한 결과다. 모두 857개다. 대응표(`../../table.json`)의 `drc-unported`·`antenna` 칸 근거이고, 나중에 이 규칙들을 KLayout으로 옮길 때 판정을 맞춰 볼 기준이다. `golden.json`은 상용 도구 출력에서만 만들었고, 손으로 고치지 않는다.

## 지금 이 golden이 하는 일과 하지 않는 일

- 이 규칙들은 KLayout 구현이 없다. 그래서 `reliability.py check`(PR마다 KLayout 판정과 golden 비교)는 이 파일을 읽지 않는다. `meta.pending`이 `true`인 golden은 `check`가 건너뛴다.
- 대신 `python scripts/asic/reliability.py check-pending`이 fixture 정의(`scripts/asic/drc_cases_pending.py`)와 이 golden이 1:1인지만 확인한다. 정의 857개와 golden 857개가 같은 이름·같은 `case_sha256`·같은 규칙이어야 하고, Calibre가 판정한 855개는 정의의 `fail`과 같아야 한다. Calibre가 입력을 거부한 2개는 사유가 붙은 제외라서 의도를 비교하지 않는다.
- 규칙 하나를 KLayout으로 옮기면, 그 규칙의 fixture를 `scripts/asic/drc_cases.py`로 옮기고 이 golden의 해당 항목을 새 기준점 폴더의 fixture golden으로 옮긴다(기준점 PR). 그때부터 `check`가 그 규칙을 비교한다.

## 묶음

| 묶음 | 내용 | fixture | Calibre 결과 | 입력 묶음 sha256 |
| --- | --- | --- | --- | --- |
| C1a | well·active·poly·주입층·접점 규칙 31개, `SKEW`, 전역 플래그 `ACUTE`·`NONSIMPLE` | 229 | 위반 111, 위반 없음 116, 입력 거부 2 | `c1a-fixtures.tar.gz` `69f0e00051546ae97619ad0ab61ffc9f8fe5c8fed8b7a7b1dd620bef4a21a10f` |
| C1b | 금속·via·pad 간격·둘러싸기 규칙 17개(228개) + ANT deck 12개 검사(102개) | 330 | 위반 166, 위반 없음 164 | `c1b-fixtures.tar.gz` `5d6537293f63eb7205c77983662443cc0800197d99a654d31a52e705230eec9e` |
| C1c | 소자 인식 규칙 64개(저항·PIP 커패시터·BJT·ESD·래치업·다이오드) | 298 | 위반 171, 위반 없음 127 | `c1c-fixtures.tar.gz` `76d120fdd2fd826e1b7fb79eb8602ad345e2ace5203eb5e23eb5f4b61d6aeef9` |

DRC 쪽 규칙은 `verification/asic/drc-rules.json`에서 `unported`인 113개 전부와 `ACUTE`·`NONSIMPLE`이다. 전역 `OFFGRID` 플래그용 fixture는 이 묶음에 없다.

## 의도와 Calibre 판정

fixture의 `fail`은 우리가 deck을 읽고 세운 가설이었다. Calibre가 판정한 855개 중 852개가 가설대로였다. 다른 3개는 정의의 `fail`을 Calibre 판정에 맞춰 고쳤다(`drc_cases_pending.py`의 `CORRECTIONS`). golden 항목에는 Calibre가 실제로 읽은 정의의 해시를 `run_case_sha256`으로 남겼다. GDS는 도형(`shapes`·`hierarchy`·`dbu`)만으로 만들어지므로 `fail`을 고쳐도 Calibre가 읽은 GDS는 같다.

Calibre가 입력을 거부한 2개(0225·0226)는 고치지 않았다. 정의는 Calibre가 읽은 그대로이고(`case_sha256` = manifest 값), golden에는 `calibre` = `refused`와 Calibre 오류 문구가 사유로 남는다. 첫 묶음의 `0169`·`0170`(dbu)과 같은 사유가 붙은 제외다. 이 저장소에서 `raises`는 우리 GDS 작성기나 KLayout이 오류를 내야 한다는 뜻이라(`drc_fixture_test.py`), Calibre의 입력 거부를 `raises`로 적지 않는다.

| fixture | 가설 | Calibre | 고친 값 |
| --- | --- | --- | --- |
| C1a `0225-NONSIMPLE-bow-tie` | NONSIMPLE 경고 | 입력 거부: `Non-orientable boundary at location (0,0) in cell fixture on layer 32 datatype 0.` | 고치지 않음(사유가 붙은 제외) |
| C1a `0226-NONSIMPLE-orthogonal-self-crossing` | NONSIMPLE 경고 | 입력 거부: `Non-orientable boundary at location (0,-2) …` | 고치지 않음(사유가 붙은 제외) |
| C1a `0227-NONSIMPLE-self-touching-vertex` | 위반(꼭짓점 하나로 닿은 두 사각형) | 경고 없음 | `fail` = false |
| C1b `0315-ANT_06_01-boundary` | 위반 없음(정확한 산술로 한계와 같음, deck은 `>`) | 위반 124 | `fail` = true |
| C1b `0323-ANT_06_02-boundary` | 위반 없음(같은 이유) | 위반 124 | `fail` = true |

- 자기 교차 다각형은 Calibre가 NONSIMPLE 경고를 내는 대신 입력 자체를 거부한다(1차 변형본 대조의 81개 거부와 같은 오류).
- ANT_06의 계수 83.33은 이진수로 정확하지 않아, 정확히 한계와 같은 도형에서 Calibre는 위반을 냈다. 한계보다 0.01 µm 작은·큰 도형은 가설대로다.
- C1a에서 `SCONNECT conflict. Multiple stamping occurred.` 경고가 16개 fixture에 나왔다(NSD·PSD가 한 ACT에 맞닿은 도형 등). 판정에는 쓰지 않고 해당 항목의 `runtime_warnings`에 그대로 적었다.

## 실행 조건

| 항목 | 값 |
| --- | --- |
| 실행일 | 2026-11-28 |
| 도구 | Calibre `v2023.4_17.10` |
| DRC deck | 키트 `Calibre/DRC/NSPL_0p5um_Analog_CMOS_2P3M_5V_V1.1_DRC.cal` 무수정, sha256 `6c01207311236d148dc183576fa8f5156e1a21d40a19609322c810fa919c4f0f` (`scripts/asic/drc_catalog.py`의 `SOURCE_SHA`) |
| ANT deck | 키트 `Calibre/ANT/NSPL_0p5um_Analog_CMOS_2P3M_5V_V1.1_ANT.cal` 무수정, sha256 `80dc257e6778121ab9a61a444d0e82c79999dc785d8e6aa5a6a2a5318c7b94b5` (1차 C3 실행의 deck 해시와 같음) |
| header | 키트 `drc_header.cal`·`ant_header.cal`에서 최상위 셀 이름만 `fixture`로 바꿈. 결과 수 제한 없음(`DRC MAXIMUM RESULTS ALL`) |
| 실행 방식 | fixture GDS 하나마다 `calibre -drc -hier header.cal` 한 번(857회). C1b의 ANT fixture 102개는 ANT deck, 나머지는 DRC deck |
| 결과 수 | C1a·C1c는 `.rep`의 계층 결과 수, C1b는 평면 결과 수. `ACUTE`·`NONSIMPLE`은 RULECHECK가 아니라서 `.rep`의 RUNTIME WARNINGS 줄 수로 셌다. 판정은 대상 규칙의 발동 여부만 쓴다 |
| fixture 정의 | `scripts/asic/drc_cases_pending_c1a.py`·`_c1b.py`·`_c1c.py`. 저장소 밖에서 만든 정의 파일을 그대로 옮겼다(C1c는 줄 끝만 CRLF → LF). 각 정의의 `case_sha256`은 각 묶음 manifest의 값과 857개 모두 같다 |

묶음별 manifest·결과 CSV·정의 파일의 sha256은 `golden.json`의 `meta.groups`에 있다. 원본 보고서(`.rep`)·로그·GDS 묶음은 저장소 밖 근거 묶음(2026-11-28, 위 sha256)에 보관한다. 서버 이름·주소·계정·경로는 넣지 않는다(SPEC 0019).

## 만든 방법

묶음마다 결과 CSV(`c1a_counts.csv`, `c1b_results.csv`, `c1c_counts.csv`; 열 `gds,target_rule,target_rule_count,other_rules_fired,status,calibre_exit,run_ms`)와, `drc_cases_pending.records()`에서 만든 `{"records": [{gds, rule, case_sha256}]}`를 `reliability.import_calibre`에 넣었다. 거부된 2개의 사유는 같은 실행의 Calibre 로그 첫 `ERROR:` 줄이다. 세 묶음의 `fixtures`를 이어 붙이고, 항목마다 `group`·`deck`(DRC/ANT)을 더했다. 고친 3개에는 `run_case_sha256`·`correction`을, C1a의 경고가 있는 항목에는 `runtime_warnings`를 더했다. 나머지 항목 형식(`gds`·`rule`·`case_sha256`·`calibre`·`target_count`·`other_rules`·`refused_reason`)은 `drc-fixtures-20261128/golden.json`과 같다. 만든 뒤 `python scripts/asic/reliability.py check-pending`으로 857 대 857 일치(제외 2)를 확인했다.
