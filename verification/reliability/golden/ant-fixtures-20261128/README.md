# 키트 ANT deck 검사의 Calibre golden (2026-11-28)

키트의 별도 Calibre ANT deck 12개 검사(RULECHECK)마다 만든 fixture 102개를 Calibre로 한 번씩 검사한 결과다. 대응표(`../../table.json`)의 `antenna` 칸 근거다. KLayout 구현은 `scripts/asic/drc_antenna.py`, fixture 정의는 `scripts/asic/drc_cases.py`의 끝부분(`0451`~`0552`)이다. `golden.json`은 상용 도구 출력에서만 만들었고, 손으로 고치지 않는다.

## 어디서 왔나

- 2026-11-28 C1b 묶음의 Calibre 실행 결과다. 처음에는 미구현 규칙의 pending golden(`../drc-unported-20261128/golden.json`)에 있었다.
- ANT deck을 KLayout으로 옮기면서, 그 파일에서 `deck`이 `ANT`인 항목 102개를 순서·내용 그대로 이 파일로 옮겼다. 원본 파일은 고치지 않았다(기존 golden 폴더는 고치지 않는다, `../../CHECKPOINT.md` 3절). 원본 파일 sha256(줄 끝 LF)은 `meta.moved_from_sha256` = `cd3c3c67a37b82dc131a2e80a747c28a3fd1c8dc0176d936f21d01a0c12e02c1`이다.
- 새 Calibre 실행은 없다. 도구(`v2023.4_17.10`), ANT deck(키트 `Calibre/ANT/NSPL_0p5um_Analog_CMOS_2P3M_5V_V1.1_ANT.cal` 무수정, sha256 `80dc257e6778121ab9a61a444d0e82c79999dc785d8e6aa5a6a2a5318c7b94b5`), header, 실행 방식(GDS 하나마다 `calibre -drc -hier` 한 번)은 원본 README와 같다.
- `python scripts/asic/reliability.py check-pending`은 pending golden에 남은 이 102개를 `moved`로 센다. 12개 규칙이 `drc_cases_pending.py`의 `MOVED_RULES`에 있고 `drc-rules.json`의 `antenna_rules`에서 verified이며, pending 정의가 없고, 이 파일에 같은 `case_sha256`·규칙·Calibre 판정이 있어야 한다. 하나라도 어긋나면 실패다.

## 항목

- 형식은 원본 그대로다: `group`, `gds`(Calibre가 읽은 C1b GDS 이름), `rule`, `deck`, `case_sha256`, `calibre`, `target_count`, `other_rules`, `refused_reason`.
- `case_sha256`는 `drc_cases.py` fixture 정의의 해시와 102개 모두 같다. 순서도 같다.
- ANT_06 등호 경계 2개(`0315-ANT_06_01-boundary`, `0323-ANT_06_02-boundary`)는 Calibre 판정(위반 124)으로 고친 정의의 해시다. Calibre가 읽은 정의의 해시는 `run_case_sha256`에, 고친 이유는 `correction`에 있다. GDS는 도형만으로 만들어지므로 두 정의의 GDS는 같다.
- Calibre 판정: 위반 45, 위반 없음 57, 입력 거부 0.

## KLayout 대조 (2026-11-28, KLayout 0.28.16)

`reliability.py check`가 PR마다 하는 대조와 같다.

```
python scripts/asic/drc_selftest.py --out 폴더
python scripts/asic/reliability.py check --selftest 폴더/selftest.json --out 결과폴더
```

- 12개 검사 모두 `match`, fixture 102개 중 102개가 대상 검사 발동 여부에서 Calibre와 같다. 제외 0.
- 대상 밖 검사 발동(`other_rules`)도 102개 모두 Calibre와 같았다(예: `0260`에서 ANT_02_1, `0321`에서 ANT_05_1). 판정에는 쓰지 않고 기록만 한다.
- 마커 수는 다르다. KLayout은 위반한 넷 하나를 1개로 세고, Calibre는 결과 다각형 수를 센다(예: `0315` Calibre 124, KLayout 1). 판정에는 쓰지 않는다.

### 등호 경계의 산술

deck은 모두 `>`로 비교한다. KLayout 구현은 넓이·둘레를 정수 dbu로 재고 `dbu² / 정밀도²`, `dbu / 정밀도`(정밀도 1000)로 바꾼 뒤, deck 식을 같은 연산 순서의 배정밀도로 계산한다. 12개 검사의 등호 경계 fixture에서 이 계산은 Calibre와 같다.

| 경계 fixture | 식 | 계산값 | 판정 |
| --- | --- | --- | --- |
| ANT_01·02_x·03_x·04·05_x `boundary` | 비율 = 한계, 또는 차 = 0 | 한계와 정확히 같음 | 위반 없음 (Calibre 같음) |
| ANT_06_01·06_02 `boundary` | `(79.165 - (0.5 * ((1.0 * 83.33) + 75))) * 1` | `1.42e-14` | 위반 (Calibre 124) |

`dbu × 1e-6`처럼 곱해서 바꾸면 ANT_06 경계의 차가 0이 되어 Calibre와 달라진다. 그래서 나눗셈으로 바꾼다.

## 칩 3건 대조 (같은 GDS)

Calibre 쪽은 `../chip-openflow-20261128/summary.json`·`../chip-v2-20261128/summary.json`의 ANT 결과(모두 0건)다. 같은 sha256의 GDS에 KLayout antenna 검사를 실행했다.

```
SSC_DRC_PROFILE=antenna SSC_GDS=GDS SSC_TOP=최상위셀 SSC_DRC_OUT=결과.json klayout -b -r scripts/asic/drc.py
```

| GDS | sha256 | Calibre ANT | KLayout antenna |
| --- | --- | --- | --- |
| 코어 `v_ternary8_top` (오픈소스 흐름) | `fa6ab910b7f03fd4c966c9c19b2455fd7f26297614c1f20ccb221fed9b09ea93` | 0건 | 0건 |
| SOP28 칩 `ternary8_sop28` (오픈소스 흐름) | `967bcad67c0f3a4df18e2faec2c10df65c33b27f6da0fef8794ce6168c550fdb` | 0건 | 0건 |
| v2 칩 `v_ternary8_chip_top_ns` (seal ring 없음) | `521a5010da74cd8ca75744ebef7141b9cadfd3c9fe155488d561f3132c622e58` | 0건 | 0건 |
| v2 칩 `v_ternary8_chip_top` (seal ring 있음) | `be4720283cbfc23a9bdca9e9e65609ce1cff60982f90c904a7191d0a3574f9c1` | 0건 | 0건 |

검사마다 게이트가 있는 넷 중 가장 큰 식 값(한계보다 크면 위반)은 아래와 같다. 0건이 한계 근처의 우연이 아님을 보이는 기록이다.

| 검사 | 한계 | 코어 | SOP28 칩 | v2 칩(두 판 같음) |
| --- | --- | --- | --- | --- |
| ANT_01 | 200 | 4.8 | 4.8 | 4.8 |
| ANT_02_1 | 400 | 1.25 | 2.37 | 6.67 |
| ANT_02_2 | 400 | 126.26 | 74.17 | 41.09 |
| ANT_02_3 | 400 | 12.82 | 0 | 0 |
| ANT_03_1 | 0 | -9900 | -6820 | -6820 |
| ANT_03_2 | 0 | -9900 | -9900 | -9900 |
| ANT_03_3 | 0 | -135000 | -734324.8 | -734400 |
| ANT_04 | 10 | 0.24 | 0.24 | 0.24 |
| ANT_05_1 | 20 | 0.14 | 0.41 | 0.41 |
| ANT_05_2 | 20 | 0.43 | 0.43 | 0.43 |
| ANT_06_01 | 0 | -337.5 | -232.5 | -232.5 |
| ANT_06_02 | 0 | -337.5 | -337.5 | -337.5 |

PR마다 다시 맞추는 것은 fixture 대조다. 칩 대조는 기준점에서만 다시 한다. 흐름(`run_asic.py --gate`)은 PR마다 새로 만든 코어·칩 GDS에서 antenna 0건을 확인한다(`asic-antenna`, `asic-chip-antenna`). v2 칩 GDS는 저장소에 넣지 않는다. 서버 이름·주소·계정·경로는 넣지 않는다(SPEC 0019).
