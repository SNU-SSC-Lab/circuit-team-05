# DRC 금속·via·PAD 규칙 fixture Calibre golden (2026-11-28, 묶음 1)

키트 DRC deck의 금속·via·PAD 규칙 17개마다 만든 fixture 228개를 Calibre로 한 번씩 검사한 결과다. 대응표(`../../table.json`)의 `drc-fixtures` 칸 근거 중 하나다. KLayout 구현은 `scripts/asic/drc_geometry.py`·`drc_ports.py`, fixture 정의는 `scripts/asic/drc_cases.py`의 끝부분(`0553`~`0780`)이다. 이식 내용은 SPEC 0021(`docs/specs/0021-drc-port-batch1.md`)에 있다. `golden.json`은 상용 도구 출력에서만 만들었고, 손으로 고치지 않는다.

## 어디서 왔나

- 2026-11-28 C1b 묶음의 Calibre 실행 결과다. 처음에는 미구현 규칙의 pending golden(`../drc-unported-20261128/golden.json`)에 있었다.
- 17개 규칙을 KLayout으로 옮기면서, 그 파일에서 17개 규칙의 항목 228개를 순서·내용 그대로 이 파일로 옮겼다. 원본 파일은 고치지 않았다(기존 golden 폴더는 고치지 않는다, `../../CHECKPOINT.md` 3절). 원본 파일 sha256(줄 끝 LF)은 `meta.moved_from_sha256` = `cd3c3c67a37b82dc131a2e80a747c28a3fd1c8dc0176d936f21d01a0c12e02c1`이다.
- 새 Calibre 실행은 없다. 도구(`v2023.4_17.10`), DRC deck(키트 `Calibre/DRC/NSPL_0p5um_Analog_CMOS_2P3M_5V_V1.1_DRC.cal` 무수정, sha256 `6c01207311236d148dc183576fa8f5156e1a21d40a19609322c810fa919c4f0f`), header, 실행 방식(GDS 하나마다 한 번)은 원본 README와 같다.
- `python scripts/asic/reliability.py check-pending`은 pending golden에 남은 이 228개를 `moved`로 센다. 17개 규칙이 `drc_cases_pending.py`의 `MOVED_RULES`에 있고 `drc-rules.json`에서 verified이며, pending 정의가 없고, 이 파일에 같은 `case_sha256`·규칙·Calibre 판정이 있어야 한다. 하나라도 어긋나면 실패다.

## 항목

- 형식은 원본 그대로다: `group`(모두 C1b), `gds`(Calibre가 읽은 C1b GDS 이름), `rule`, `deck`(모두 DRC), `case_sha256`, `calibre`, `target_count`, `other_rules`, `refused_reason`.
- `case_sha256`는 `drc_cases.py` fixture 정의의 해시와 228개 모두 같다. 순서도 같다.
- Calibre 판정이 정의의 기대값과 다른 fixture는 없다(고친 정의 0, `run_case_sha256` 없음).
- Calibre 판정: 위반 121, 위반 없음 107, 입력 거부 0.

| 규칙 | fixture | 규칙 | fixture |
| --- | --- | --- | --- |
| `8.MET1.S1` | 15 | `10.MET2.S2` | 16 |
| `8.MET1.S2` | 16 | `11.VIA2.S2` | 13 |
| `9.VIA1.S2` | 13 | `11.VIA2.E1`~`E4` | 각 12 |
| `9.VIA1.E1`~`E4` | 각 12 | `12.MET3.S1` | 15 |
| `10.MET2.S1` | 15 | `12.MET3.S2` | 16 |
| `13.PAD.P` | 13 | | |

## KLayout 대조 (2026-11-28, KLayout 0.28.16)

`reliability.py check`가 PR마다 하는 대조와 같다.

```
python scripts/asic/drc_selftest.py --out 폴더
python scripts/asic/reliability.py check --selftest 폴더/selftest.json --out 결과폴더
```

- 17개 규칙 모두 `match`, fixture 228개 중 228개가 대상 규칙 발동 여부에서 Calibre와 같다. 제외 0.
- 대상 밖 규칙 발동(`other_rules`)도 228개 모두 Calibre와 같았다(KLayout 구현 규칙 범위). 예: 폭 10.00 µm 두 선의 S1 fixture에서 S2 발동, 꼬리 걸친 via에서 E1·E2 둘 다 발동. 판정에는 쓰지 않고 기록만 한다.
- 마커 수는 다를 수 있다. 판정에는 쓰지 않는다.

### deck 해석을 정한 fixture

| fixture | Calibre | 정한 것 |
| --- | --- | --- |
| `0014-8.MET1.S1-narrow-tail-of-wide-below`, `0030-8.MET1.S2-narrow-tail-of-wide-gap-mid` | 위반 / 위반 없음 | `WITH WIDTH`는 다각형 일부를 고른다(20 µm 판의 2 µm 꼬리는 좁은 쪽) |
| `0006`·`0021` 등 width-10.00 / width-9.99 | 10.00은 넓은 쪽, 9.99는 좁은 쪽 | 폭 10.00 µm는 `>= 10`에 들어간다 |
| `0015-8.MET1.S2-below` 등 S2 위반 fixture | 위반 | `EXT MET1UP10 MET1`은 겹친 변에 가려지지 않는다(KLayout은 차폐 없이 잰다) |
| `0128-9.VIA1.E1-straddles-wide-narrow-cut` 등 | E1·E2 둘 다 위반 | 넓은/좁은 경계에 걸친 via는 양쪽 둘러싸기 위반(OVERLAP) |
| `0101-9.VIA1.S2-3x3-s0.40-degenerate` | 위반 없음 | 키운 배열 묶음이 정확히 4.8 µm이면 UNDEROVER로 사라진다 |
| `0218-13.PAD.P-gap-39.98-grown-abut`, `0217-…-gap-39.99` | 위반 / 위반 없음 | 19.99 µm씩 키운 PAD가 맞닿으면 이어진다 |

## 변형본·칩 대조

- 변형본 golden 두 개(`../drc-mutations-20261128/`, `../drc-mutations-20261128b/`)에도 이 17개 규칙의 Calibre 결과가 들어 있다(deck 전체 실행). `check-mutations --kit`의 대조 결과는 SPEC 0021과 대응표 `drc-mutations` 행에 있다.
- 변형본에서 Calibre가 이 17개 규칙을 낸 것은 좁은 쪽 규칙(`*.S1`, `9.VIA1.E1`·`E3`, `11.VIA2.E1`·`E3`, `9.VIA1.S2` 한 번)뿐이다. 넓은 쪽 규칙(`*.S2`, `E2`·`E4`), `11.VIA2.S2`, `13.PAD.P`는 변형본에서 한 번도 발동하지 않았다. 이 규칙들의 실제 형상 근거는 "둘 다 위반 없음"뿐이고, 위반 쪽 근거는 fixture뿐이다.
- 칩 GDS 네 개(`../chip-openflow-20261128/`, `../chip-v2-20261128/`와 같은 sha256)에서 KLayout 구현 규칙 113개는 모두 0건이다. 같은 GDS의 Calibre DRC는 0·0·0건, v2 seal ring 판만 1건(`1.PWL.bad1`, 아직 KLayout에 없음)이다.

서버 이름·주소·계정·경로는 넣지 않는다(SPEC 0019).
