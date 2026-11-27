# DRC 변형본 Calibre golden (2026-11-28)

키트 셀의 실제 형상을 한 도형씩 바꾼 변형본(mutation) GDS 695개를 Calibre로 한 번씩 검사한 결과를 묶은 고정 근거 파일이다. 손으로 그린 fixture(`golden/drc-fixtures-20261128/`)는 규칙마다 경계값을 시험하지만, 실제 셀에서 도형이 어긋나는 경우(일부만 겹침 등)는 다루지 못한다. `python scripts/asic/reliability.py check-mutations`가 같은 변형본을 다시 만들어 KLayout 판정이 이 결과와 같은지 맞춰 본다(SPEC 0019 2절). 이 폴더의 `golden.json`은 상용 도구 출력에서만 만들었고, 손으로 고치지 않는다.

## 실행 조건

| 항목 | 값 |
| --- | --- |
| 실행일 | 2026-11-28 |
| 도구 | Calibre `v2023.4_17.10` |
| DRC deck | 키트 `Calibre/DRC/NSPL_0p5um_Analog_CMOS_2P3M_5V_V1.1_DRC.cal` 무수정, sha256 `6c01207311236d148dc183576fa8f5156e1a21d40a19609322c810fa919c4f0f` (`scripts/asic/drc_catalog.py`의 `SOURCE_SHA`와 같은 파일) |
| header | 키트 `drc_header.cal`에서 최상위 셀 이름만 `mut`로 바꿈. 결과 수 제한 없음(`DRC MAXIMUM RESULTS ALL`) |
| 실행 방식 | GDS 하나마다 Calibre를 한 번씩 실행(695회, 병합 없음) |
| 입력 묶음 | `c2-mutations-695.tar.gz` sha256 `0dbbcf4dcbcbae612b51e8d76da887a81e9524e3636ade5929ae9a45eaeb2225` |
| 변형본 생성 | `scripts/asic/mutate.py`, seed `20261128`, 셀당 변형 6개(+ 원본 1개), 공개 키트(`NSPL_05CMOS_PDK_260820.tar.gz` sha256 `2e49115a08f6af96c1f8433130ad4316551b5eba9001a3133905b544166af954`)의 표준셀 GDS와 GPIO GDS |

서버 이름·주소·계정·경로와 원본 로그는 공개 저장소에 넣지 않는다(SPEC 0019).

## 변형본

- 원본 GDS 두 개(`NSPL_0p5um_Digital_CMOS_2P3M_5V_V1p1_12T_std.gds` 238개, `ETRI_NSPL_GPIO_250610.gds` 457개)의 셀마다 평탄화한 최상위 셀 `mut`를 만든다. 변형 0은 원본 그대로(105개)이고, 나머지는 도형 하나를 x·y로 옮기기(`shift_x`, `shift_y`), 키우기(`grow`), 줄이기(`shrink`), 지우기(`delete`) 중 하나로 0.05~0.8 µm 바꾼다(590개).
- GDS 파일에는 만든 시각이 들어가 바이트가 실행마다 달라진다. 그래서 변형본마다 **형상 해시**(`geometry_sha256`)를 남긴다. dbu와, 층/datatype마다 모든 다각형(사각형·path 포함, 글자 제외)의 정수 좌표 목록을 정렬해 sha256을 낸 값이다(`mutate.py`의 `geometry_sha256`).
- `mutate.py generate --kit 키트폴더`로 다시 만든 695개의 형상 해시가 Calibre가 읽은 입력 묶음의 695개와 모두 같고, 변형 내용(셀·변형 번호·연산·크기·층)도 모두 같다는 것을 확인했다(2026-11-28, KLayout 0.28.16). 형상 해시를 계산한 KLayout 버전은 `meta.klayout_version`에 적었다. `check-mutations`는 실행한 KLayout 버전도 `result.json`에 남긴다.

## 결과

| Calibre 판정 | GDS 수 | 뜻 |
| --- | --- | --- |
| `ok` | 614 | 원본 105개 + 변형 509개. 그중 479개에서 규칙이 1개 이상 발동 |
| `refused` | 81 | 변형된 다각형이 스스로 교차해 Calibre가 GDS를 읽다가 멈춤(`Non-orientable boundary ...`). 규칙 판정이 아니라 입력 거부라서 대조에서 사유가 붙은 제외로 센다 |

- `rules_fired`는 Calibre가 그 GDS에서 위반을 낸 모든 규칙과 위반 수다. 원본(변형 0) 중 56개도 이미 규칙을 발동한다(예: FILLX1~4의 `5.NSD.bad1`·`6.PSD.bad1`, GPIO 하위 셀의 `1.PWL.bad1`). 그대로 기록했다.
- `polygons`가 0인 5개(`0250-CONT-v5`, `0564`·`0565`·`0566`·`0568-VIA2`)는 변형이 셀의 유일한 도형을 지워 최상위 셀이 비었다. Calibre는 구현하지 않은 `1.PWL.bad1`만 냈고, KLayout DRC는 빈 최상위 셀을 입력 오류로 거부하므로 대조에서 사유가 붙은 제외로 센다. 빈 GDS라도 Calibre가 `verified` 규칙을 냈다면 제외하지 않고 불일치로 센다(빈 도면에서는 KLayout 규칙이 발동할 수 없다).
- 대조 기준은 GDS마다 `verified` 규칙(`verification/asic/drc-rules.json`)이 **위반을 냈는지(있음/없음)** 뿐이다. 마커 수는 기록만 한다.
- 2026-11-28 첫 대조(614개 중 KLayout가 읽은 609개 × 구현 96개 규칙 = 58,464 판정)에서 13건이 Calibre만 위반이었다. 모두 `7.CONT.E1/E2/E3`에서 접점이 둘러싸는 층에 일부만 겹친 경우다. deck의 `ENC … OVERLAP`은 이런 도형을 위반으로 보는데 KLayout 구현이 놓치고 있었고, 같은 PR에서 고쳤다. 경계 사례는 fixture `0427`~`0450`과 그 Calibre 결과(`golden/drc-fixtures-20261128b/`)로 확인했다.

## `golden.json` 형식

- `meta`: 위 실행 조건(`calibre_version`, `deck_sha256`, `corpus_tarball_sha256`, `run_date`), 형상 해시를 계산한 `klayout_version`, 생성 조건(`seed`, `per_cell`, `sources`, `generator`), 해시 방식(`geometry_hash`).
- `mutations[]`: `gds`, `source`, `cell`, `variant`, `op`(`original`이 아니면 `delta_um`, `layer`, `near_um`도), `geometry_sha256`, `polygons`, `calibre`(`ok`/`refused`), `rules_fired`(규칙 이름: 위반 수), `refused_reason`.

## 만든 방법

```
python scripts/asic/mutate.py hash --gds-dir 입력묶음폴더 --out geometry.json
python scripts/asic/reliability.py import-mutations --counts c2_counts.csv --manifest 입력묶음폴더/manifest.json \
  --geometry geometry.json --out verification/reliability/golden/drc-mutations-20261128/golden.json \
  --calibre-version v2023.4_17.10 \
  --deck-sha256 6c01207311236d148dc183576fa8f5156e1a21d40a19609322c810fa919c4f0f \
  --corpus-tarball-sha256 0dbbcf4dcbcbae612b51e8d76da887a81e9524e3636ade5929ae9a45eaeb2225 --run-date 2026-11-28 \
  --klayout-version 0.28.16
```

`c2_counts.csv`는 GDS마다 Calibre가 발동한 규칙(`규칙:수;…`), 종료 코드, 실행 시간, 거부 사유를 모은 표다. 이 입력 파일들은 저장소 밖에 보관한다. `import-mutations`는 기존 파일을 덮어쓰지 않는다. 결과를 바꿔야 하면 기준점 절차로 새 실행 날짜의 폴더를 만든다.

## 대조 실행

```
python scripts/asic/reliability.py check-mutations --golden verification/reliability/golden/drc-mutations-20261128/golden.json \
  --kit 키트폴더/NSPL_05CMOS_PDK_260820 --out 새폴더
```

`--kit` 대신 `--gds-dir 변형본폴더`로 이미 있는 변형본을 쓸 수 있다. 어느 쪽이든 형상 해시를 다시 계산해 golden과 같은 GDS만 KLayout DRC(`scripts/asic/drc.py`, `SSC_DRC_PROFILE=expanded`, 최상위 셀 `mut`)로 검사한다. 형상 해시가 다르거나 GDS·KLayout 결과가 없으면(GDS 하나당 600초를 넘긴 KLayout 실행 포함) 같은 입력을 검사했다고 볼 수 없으므로 실패로 센다. 불일치가 하나라도 있으면 종료 코드 1이고, `summary.md`에 GDS·규칙·양쪽 위반 수를 적는다.
