# v2 칩 Calibre 검사 (2026-11-28)

Cadence 도구로 만든 v2 칩 `v_ternary8_chip_top`을 Calibre로 DRC·ANT·LVS 검사한 결과와, 같은 GDS에 KLayout 구현 규칙을 돌린 결과 요약이다. 대응표(`../../table.json`)의 `drc-chip-v2` 칸 근거다(SPEC 0019 2절). v2 칩 GDS는 저장소에 넣지 않는다(2026-11-27 결정). 여기에는 해시와 판정 요약만 둔다. 이 칸은 PR마다 다시 대조하지 않고 기준점에서만 다시 맞춘다.

## 실행 조건

| 항목 | 값 |
| --- | --- |
| 실행일 | 2026-11-28 |
| 도구 | Calibre `v2023.4_17.10` |
| deck | 키트 Calibre DRC·ANT·LVS deck 무수정(DRC RULECHECK 209개). 이 실행의 deck 파일 해시는 따로 기록하지 않았다. 다음 기준점부터는 `chip-openflow-20261128`처럼 해시를 남긴다 |
| KLayout | 같은 GDS에 저장소의 구현 규칙 96개를 실행 |

## 입력 GDS와 결과

| GDS | seal ring | sha256 | Calibre DRC | Calibre ANT | Calibre LVS | KLayout 구현 규칙 |
| --- | --- | --- | --- | --- | --- | --- |
| `v_ternary8_chip_top_ns` | 없음 | `521a5010da74cd8ca75744ebef7141b9cadfd3c9fe155488d561f3132c622e58` | 0건 | 0건 | CORRECT | 0건 |
| `v_ternary8_chip_top` | 있음 | `be4720283cbfc23a9bdca9e9e65609ce1cff60982f90c904a7191d0a3574f9c1` | 1건 (`1.PWL.bad1`) | 0건 | CORRECT | 0건 |

- seal ring 판의 `1.PWL.bad1`은 KLayout에 아직 옮기지 않은 규칙(`unported`)이다. 그래서 KLayout 0건과 Calibre 1건의 차이는 구현 규칙의 불일치가 아니라 미검증 목록 `drc-unported-rules`에 속한다.
- 구현 규칙 범위에서는 두 GDS 모두 KLayout 0건 ↔ Calibre 0건으로 거짓 위반·놓친 위반이 없다.

서버 이름·주소·계정·경로와 원본 로그는 공개 저장소에 넣지 않는다(SPEC 0019).
