# DRC 변형본 Calibre golden, 2차 (2026-11-28)

키트 셀과 오픈소스 흐름 코어 GDS의 30×30 µm 창을 한 번씩만 고친 변형본 GDS 800개를 Calibre로 GDS마다 한 번씩 검사한 결과다. 1차(`golden/drc-mutations-20261128/`)는 81개가 자기 교차 다각형이라 Calibre가 입력을 거부했다. 2차 생성기는 모든 편집을 병합 의미로 처리하고 잘못된 결과를 다시 뽑아 800개 모두 Calibre가 검사했다. `python scripts/asic/reliability.py check-mutations`가 1차와 함께 이 golden도 다시 맞춰 본다(SPEC 0019 2절). 이 폴더의 `golden.json`은 상용 도구 출력에서만 만들었고, 손으로 고치지 않는다.

## 실행 조건

| 항목 | 값 |
| --- | --- |
| 실행일 | 2026-11-28 |
| 도구 | Calibre `v2023.4_17.10` |
| DRC deck | 키트 `Calibre/DRC/NSPL_0p5um_Analog_CMOS_2P3M_5V_V1.1_DRC.cal` 무수정, sha256 `6c01207311236d148dc183576fa8f5156e1a21d40a19609322c810fa919c4f0f` (`scripts/asic/drc_catalog.py`의 `SOURCE_SHA`) |
| header | 키트 `drc_header.cal`에서 최상위 셀 이름만 `mut`로 바꿈. `DRC MAXIMUM RESULTS ALL` |
| 실행 방식 | GDS 하나마다 Calibre를 한 번씩 실행(800회, 모두 종료 코드 0) |
| 입력 묶음 | `c2v2-mutations-800.tar.gz` sha256 `ecf0263db5aa2ff527d26d4a5b07b8aebb47360f5036e1e853dc8d402784d5a1` (안의 `manifest.json` sha256 `e6b839e1362786f1691d24a73cd360df6c70d273a09a338094ff87a699b07bdf`) |
| 변형본 생성 | `scripts/asic/mutate_v2.py`, seed `20261129`. 원래 실행한 생성기 파일 sha256은 `meta.original_generator_sha256`(`05e5d01f6d5eec6da225445263fd072808db5414fd18f09ae5a6af953667f951`) |
| 원본 GDS | 표준셀 `NSPL_0p5um_Digital_CMOS_2P3M_5V_V1p1_12T_std.gds` `e42dc1fb4c9a31aaa669e8e4c3b93a4b0d6eea40a463f5eaef5dbd17b432618e`, GPIO `ETRI_NSPL_GPIO_250610.gds` `7d54a4948e775fc3a99faf157f91a3510a82c22cc134d677de83dd2214b6e971`(둘 다 공개 키트 `NSPL_05CMOS_PDK_260820.tar.gz` sha256 `2e49115a08f6af96c1f8433130ad4316551b5eba9001a3133905b544166af954` 안), 코어 `v_ternary8_top.gds` `fa6ab910b7f03fd4c966c9c19b2455fd7f26297614c1f20ccb221fed9b09ea93`(우리 오픈소스 흐름 결과, 저장소에 넣지 않음) |
| 형상 해시 계산 | KLayout `0.28.16` (`meta.klayout_version`) |

서버 이름·주소·계정·경로와 원본 로그는 공개 저장소에 넣지 않는다(SPEC 0019).

## 변형본

- 키트 셀 604개: 원본 105개(1차와 같은 셀; 라이브러리 전체 top은 원본만) + 표준셀마다 8개, GPIO 셀마다 3개 변형.
- 코어 창 196개: 코어 GDS에서 무작위 30×30 µm 창 28개(도형 20개 이상, 원점 0.05 µm 격자) + 창마다 6개 변형. 도형은 창 경계에서 하나씩 잘랐고, 접점·via는 창 안에 통째로 있는 것만 남겼다. 창 원본도 잘린 경계에서 규칙을 낼 수 있다.
- 연산: 옮기기(±), 키우기, 줄이기, 지우기, 한 변 옮기기(`edge_move`), 배선 폭을 층 최소 폭 ±0.05 µm로 좁히기(`narrow_minw`), 접점·via 복제(최소 간격 ±0.05~+0.4 µm, `dup_via`), 접점·via 지우기(`del_via`). 각 기록의 `params`, `shape_before_um`, `shapes_after_um`, `xor_area_um2`, `near_um`에 정확한 수치가 있다.
- 형상 해시(`geometry_sha256`)는 1차와 같은 방법(`mutate.py`의 `geometry_sha256`)이다.

## 재생성 확인

2026-11-28, KLayout 0.28.16에서 `mutate_v2.py generate`로 다시 만든 결과:

- 키트만(`--kit`): 604개가 입력 묶음의 키트 셀 기록과 기록 내용·형상 해시·GDS 바이트까지 모두 같다. 키트 부분은 난수를 먼저 쓰므로 코어 GDS가 있든 없든 같다.
- 키트 + 같은 코어 GDS(`--core-gds`, sha256 `fa6ab910b7f03fd4c966c9c19b2455fd7f26297614c1f20ccb221fed9b09ea93`): 800개 모두 같다.

## 결과

| 구분 | GDS 수 |
| --- | --- |
| Calibre 검사(`ok`) | 800 (거부 0) |
| 최상위 셀이 빈 GDS | 2 (`0348-CONT-v1`, `0350-CONT-v3`; Calibre는 구현하지 않은 `1.PWL.bad1`만 냄 → 사유가 붙은 제외) |

`rules_fired`는 Calibre가 그 GDS에서 위반을 낸 모든 규칙과 위반 수다. 대조 기준은 1차와 같이 GDS마다 `verified` 규칙의 발동 여부(있음/없음)뿐이다. 2026-11-28 대조(KLayout `84eb91b`): 798개 × 96개 규칙 = 76,608 판정 중 둘 다 위반 2,022, 둘 다 없음 74,586, 한쪽만 위반 0.

## CI에서 다시 만드는 범위 (코어 창은 기준점 전용)

코어 GDS는 우리 RTL과 흐름으로 만든 결과라 저장소에 없고, RTL이 바뀌면 같은 파일이 나오지 않는다. 그래서:

- `check-mutations --kit 키트폴더`는 키트 셀 604개만 다시 만들어 비교한다. 코어 창 196개는 `not_regenerated`(이번에 만들지 않음)로 세고 요약에 수와 이유를 적는다. 일치로도, 실패로도 세지 않는다.
- `--core-gds 파일`을 주면 그 파일의 sha256이 golden의 `fa6ab910b7f03fd4c966c9c19b2455fd7f26297614c1f20ccb221fed9b09ea93`과 같을 때만 창도 만들어 비교한다. 다르면(다른 RTL·흐름) 역시 `not_regenerated`이며 이유에 두 해시를 적는다. sha256이 같은데 형상 해시가 다르면 실패다.
- 키트 원본 GDS의 sha256이 golden과 다르면 실행을 멈추고 실패한다. 키트 셀 기록의 형상 해시가 다르거나 GDS·KLayout 결과가 없으면 실패다.

## `golden.json` 형식

- `meta`: 실행 조건(`calibre_version`, `deck_sha256`, `corpus_tarball_sha256`, `run_date`, `klayout_version`), 생성 조건(`seed`, `sources`(파일 이름: sha256), `params`, `redraw_reasons`, `generator`, `original_generator_sha256`), `geometry_hash`, `checkpoint_only_sources`(`["v_ternary8_top.gds"]`).
- `mutations[]`: manifest 기록 전부(`gds`, `source`, `cell`, `kind`, `variant`, `op`, 창이면 `window`·`window_um`, 변형이면 `draws`·`params`·`layer`·`shape_before_um`·`shapes_after_um`·`xor_area_um2`·`near_um`)와 `geometry_sha256`, `polygons`, `calibre`(`ok`/`refused`), `rules_fired`, `refused_reason`.

## 만든 방법

```
python scripts/asic/mutate.py hash --gds-dir 입력묶음폴더 --out geometry.json
python scripts/asic/reliability.py import-mutations --counts c2v2_counts.csv --manifest 입력묶음폴더/manifest.json \
  --geometry geometry.json --out verification/reliability/golden/drc-mutations-20261128b/golden.json \
  --generator scripts/asic/mutate_v2.py --checkpoint-only-source v_ternary8_top.gds \
  --calibre-version v2023.4_17.10 \
  --deck-sha256 6c01207311236d148dc183576fa8f5156e1a21d40a19609322c810fa919c4f0f \
  --corpus-tarball-sha256 ecf0263db5aa2ff527d26d4a5b07b8aebb47360f5036e1e853dc8d402784d5a1 \
  --run-date 2026-11-28 --klayout-version 0.28.16
```

## 대조 실행

```
python scripts/asic/reliability.py check-mutations --kit 키트폴더/NSPL_05CMOS_PDK_260820 --out 새폴더
python scripts/asic/reliability.py check-mutations --kit 키트폴더/NSPL_05CMOS_PDK_260820 --core-gds v_ternary8_top.gds --out 새폴더  # 기준점
```

`--golden`을 주지 않으면 `golden/drc-mutations-*/golden.json`을 모두 검사하고, `새폴더/<golden 폴더 이름>/`에 golden별 결과를, `새폴더/result.json`·`summary.md`에 합친 표를 쓴다.
