# DRC fixture Calibre golden (2026-11-28)

KLayout DRC 자체 시험 도형(fixture) 427개를 Calibre로 한 번씩 검사한 결과를 요약한 고정 근거 파일이다. `scripts/asic/reliability.py check`가 PR마다 현재 KLayout 판정을 이 파일과 다시 맞춰 본다(SPEC 0019 2절). 이 폴더의 `golden.json`은 상용 도구 출력에서만 만들었고, 손으로 고치지 않는다.

## 실행 조건

| 항목 | 값 |
| --- | --- |
| 실행일 | 2026-11-28 |
| 도구 | Calibre `v2023.4_17.10` |
| DRC deck | 키트 `Calibre/DRC/NSPL_0p5um_Analog_CMOS_2P3M_5V_V1.1_DRC.cal` 무수정, sha256 `6c01207311236d148dc183576fa8f5156e1a21d40a19609322c810fa919c4f0f` (`scripts/asic/drc_catalog.py`의 `SOURCE_SHA`와 같은 파일) |
| header | 키트 `drc_header.cal`에서 최상위 셀 이름만 `fixture`로 바꿈. 결과 수 제한 없음(`DRC MAXIMUM RESULTS ALL`) |
| 실행 방식 | fixture GDS 하나마다 Calibre를 한 번씩 실행(427회) |
| 입력 묶음 | `drc-fixtures-427.tar.gz` sha256 `a125b25350f984c46dde3d9c73f172bd085508ac540eddb35b86709e18a394d8` |
| fixture 생성 커밋 | `303bcb6` (`python scripts/asic/drc_selftest.py`가 만든 GDS와 `selftest.json`) |

서버 이름·주소·계정·경로와 원본 로그는 공개 저장소에 넣지 않는다(SPEC 0019).

## 결과

| Calibre 판정 | fixture 수 | 뜻 |
| --- | --- | --- |
| `fired` | 253 | 대상 규칙이 위반을 1개 이상 냈다 |
| `clean` | 172 | 대상 규칙이 위반을 내지 않았다 |
| `refused` | 2 | Calibre가 입력을 거부해 검사하지 않았다 |

- 거부된 2개는 GDS 단위(dbu)를 일부러 바꾼 시험이다. `0169-OFFGRID_MET1-finer-dbu`(dbu 0.0005)와 `0170-OFFGRID_MET1-incompatible-dbu`(dbu 0.003)에서 Calibre는 "Rule file precision 1000 is not consistent with database precision ..." 오류로 실행을 멈췄다. 대조에서는 불일치나 근거 없음이 아니라 사유가 붙은 제외(`excluded`)로 센다.
- 대조 기준은 fixture마다 **대상 규칙이 위반을 냈는지(있음/없음)** 뿐이다. 마커 수(`target_count`)와 대상 밖 규칙 발동(`other_rules`)은 기록만 하고 판정에 쓰지 않는다. 예: `0242-8.MET1.W-hole-keeps-a-thin-wall`은 KLayout 4개·Calibre 1개, `0408-7.CONT.bad1-absent`는 KLayout 1개·Calibre 2개지만 둘 다 위반 있음이므로 일치다.
- 실행된 425개 모두 `other_rules`에 `1.PWL.bad1`이 1건씩 있다. 시험 셀에 PWELL tap이 없어서 생기는 것이며, 그대로 기록했다.

## `golden.json` 형식

- `meta`: 위 실행 조건(`calibre_version`, `deck_sha256`, `fixture_tarball_sha256`, `generator_commit`, `run_date`)과 fixture 해시 출처.
- `fixtures[]`: `gds`, `rule`(대상 규칙), `case_sha256`, `calibre`(`fired`/`clean`/`refused`), `target_count`, `other_rules`(규칙 이름: 위반 수), `refused_reason`.
- `case_sha256`은 GDS 파일 해시가 아니라 fixture 정의(`scripts/asic/drc_cases.py`의 `cases()` 항목)의 해시다. GDS에는 만든 시각이 들어가 바이트가 실행마다 달라지기 때문이다. 생성기를 고쳐 정의가 바뀐 fixture는 golden이 없는 것(`no_golden`)으로 보인다.
- 2026-11-28 실행 때의 `selftest.json`에는 아직 `case_sha256`이 없었다. 그래서 가져오기 때 fixture 이름(`{번호:04}-{규칙}-{label}`)으로 `cases()` 항목을 찾아 해시를 계산했다. 계산한 커밋은 `meta.case_sha256_commit`(`2476d87`)이고, 그 커밋의 `drc_cases.py`는 `303bcb6`과 같다. 427개 이름이 모두 정확히 한 항목에 대응하는지와 기대값 필드(`rule`, `label`, `fail`, `hierarchy`, `dbu`, `raises`)가 같은지도 함께 확인했다.

## 만든 방법

```
python scripts/asic/reliability.py import --counts calibre_counts.csv --selftest selftest.json \
  --out verification/reliability/golden/drc-fixtures-20261128/golden.json \
  --calibre-version v2023.4_17.10 \
  --deck-sha256 6c01207311236d148dc183576fa8f5156e1a21d40a19609322c810fa919c4f0f \
  --fixture-tarball-sha256 a125b25350f984c46dde3d9c73f172bd085508ac540eddb35b86709e18a394d8 \
  --generator-commit 303bcb6 --run-date 2026-11-28
```

`calibre_counts.csv`는 fixture마다 대상 규칙 위반 수, 대상 밖 규칙 위반 수, Calibre 종료 코드를 모은 표이고, 거부 사유는 같은 실행의 로그 첫 `ERROR:` 줄에서 가져왔다. 이 입력 파일들은 저장소 밖에 보관한다. `import`는 기존 파일을 덮어쓰지 않는다. 결과를 바꿔야 하면 기준점 절차로 새 실행 날짜의 폴더를 만든다.
