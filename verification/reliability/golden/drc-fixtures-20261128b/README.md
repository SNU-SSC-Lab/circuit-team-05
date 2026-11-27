# DRC 둘러싸기 fixture Calibre golden (2026-11-28, 추가분)

둘러싸기 규칙 6개(`2.ACT.E2`, `2.ACT.E3`, `7.CONT.E1`, `7.CONT.E2`, `7.CONT.E3`, `13.PAD.E`)에 추가한 KLayout 자체 시험 도형(fixture) 24개(`0427`~`0450`)를 Calibre로 한 번씩 검사한 결과다. 첫 묶음 `golden/drc-fixtures-20261128/`(427개)과 같은 형식이며, `scripts/asic/reliability.py check`는 `verification/reliability/golden` 아래의 fixture golden을 모두 읽어 PR마다 다시 맞춰 본다. 이 폴더의 `golden.json`은 상용 도구 출력에서만 만들었고, 손으로 고치지 않는다.

## 왜 추가했나

실제 셀 변형본 대조(`golden/drc-mutations-20261128/`)에서 접점이 둘러싸는 층에 일부만 겹친 13건을 Calibre만 위반으로 냈다. deck의 `ENC a b < v ABUT < 90 SINGULAR OVERLAP REGION`은 이런 도형도 위반으로 본다. KLayout 구현을 고치면서 그 경계를 Calibre로 확인하려고 아래 네 가지 도형을 규칙마다 하나씩 만들었다.

| label | 도형 | Calibre |
| --- | --- | --- |
| `partial-overlap` | 안쪽 도형의 절반이 둘러싸는 층 밖으로 나감 | 6개 규칙 모두 위반 |
| `outside-no-overlap` | 둘러싸는 층이 5 µm 떨어져 겹치지 않음 | 위반 없음(재지 않음) |
| `outer-inside-inner` | 둘러싸는 층 도형이 안쪽 도형 안에 통째로 있음(13.PAD.E는 PAD 아래 금속 구멍) | 위반 없음. 단 `2.ACT.E3`은 위반: NTAP = NACT AND NWELL이라 NTAP가 NWELL 섬과 같아져 모든 변이 겹침(거리 0) |
| `near-outside` | 안쪽 도형이 둘러싸는 층 밖에 규칙 값보다 0.2 µm 가깝게 있음 | 위반 없음 |

결과: 24개 모두 `scripts/asic/drc_cases.py`의 기대값(`fail`)과 같다. `partial-overlap` 위반 수는 2.ACT.E2 2, 2.ACT.E3 1, 7.CONT.E1·E2·E3 각 2, 13.PAD.E 6이다.

## 실행 조건

| 항목 | 값 |
| --- | --- |
| 실행일 | 2026-11-28 |
| 도구 | Calibre `v2023.4_17.10` |
| DRC deck | 키트 `Calibre/DRC/NSPL_0p5um_Analog_CMOS_2P3M_5V_V1.1_DRC.cal` 무수정, sha256 `6c01207311236d148dc183576fa8f5156e1a21d40a19609322c810fa919c4f0f` (`scripts/asic/drc_catalog.py`의 `SOURCE_SHA`) |
| header | 키트 `drc_header.cal`에서 최상위 셀 이름만 `fixture`로 바꿈. 결과 수 제한 없음(`DRC MAXIMUM RESULTS ALL`) |
| 실행 방식 | fixture GDS 하나마다 Calibre를 한 번씩 실행(24회) |
| 입력 묶음 | `c8-fixtures.tar.gz` sha256 `15acbafef6f71fbf0b4357a3bb1aa82e502347fce9dc3f4e0033d011646ff8ef` (`0427`~`0438`), `c9-fixtures.tar.gz` sha256 `58c6e44f8ef30c79cf2641356cc7ba5ae5840d7359a712e20f54aa0a5597fb02` (`0439`~`0450`) |
| fixture 정의 커밋 | `756b384` (`drc_cases.py`에 24개가 모두 있는 커밋. `0427`~`0438`은 `5b1f8bf`에서 먼저 들어왔고 정의는 같다) |

두 묶음은 같은 날 같은 조건으로 따로 실행했고, 결과를 하나의 golden으로 묶었다. 서버 이름·주소·계정·경로와 원본 로그는 공개 저장소에 넣지 않는다(SPEC 0019).

## 만든 방법

두 묶음의 `calibre_counts.csv`를 한 파일로 잇고, 두 묶음의 `new_fixtures.json` 기록을 `{"records": [...]}` 하나로 합친 뒤:

```
python scripts/asic/reliability.py import --counts calibre_counts.csv --selftest selftest.json \
  --out verification/reliability/golden/drc-fixtures-20261128b/golden.json \
  --calibre-version v2023.4_17.10 \
  --deck-sha256 6c01207311236d148dc183576fa8f5156e1a21d40a19609322c810fa919c4f0f \
  --fixture-tarball-sha256 "c8-fixtures.tar.gz 15acbafe…6ff8ef (0427-0438); c9-fixtures.tar.gz 58c6e44f…97fb02 (0439-0450)" \
  --generator-commit 756b384 --run-date 2026-11-28
```

(`--fixture-tarball-sha256`에는 위 표의 전체 해시 두 개를 그대로 넣었다.) `new_fixtures.json`에 `case_sha256`이 있으므로 해시는 기록에서 바로 가져왔다(`meta.case_sha256_from` = `selftest`). 형식은 첫 묶음 README의 `golden.json` 형식과 같다. Calibre가 거부한 fixture는 없다.
