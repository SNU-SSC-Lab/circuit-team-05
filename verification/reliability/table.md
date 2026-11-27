# 신뢰성 대응표

오픈소스 도구 판정과 상용 도구 판정을 단계별로 맞춰 본 근거다(SPEC 0019 2절). 이 파일은 `table.json`에서 만든다. 손으로 고치지 말고 `table.json`을 고친 뒤 `python scripts/asic/reliability.py render --table verification/reliability/table.json --out verification/reliability/table.md`를 실행한다.

- 판정: 일치(`match`) · 불일치(`mismatch`) · 근거 없음(`no_evidence`, 미검증 목록에 있음).
- 근거 경로는 `verification/reliability/` 기준이다. 근거 없음 칸은 `unverified.json`의 항목 id를 적는다.
- 수치 차이(마커 수·타이밍 등)는 기록만 하고 판정 조건으로 쓰지 않는다.

| 단계 | 오픈소스 (PR마다) | 상용 기준 (기준점) | 판정 | 범위 | 현재 근거 | CI가 PR마다 확인하는 것 | 근거 파일·미검증 항목 | 갱신일 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DRC 규칙 판정 | KLayout 0.28.16 구현 규칙 96개 | Calibre v2023.4_17.10, 키트 DRC deck 무수정(sha256 6c012073…c4f0f) | **일치** | 구현 96개 규칙의 fixture 427개 | 427개 중 425개 대상 규칙 발동 여부 일치, 2개(0169·0170, dbu 시험)는 Calibre가 입력을 거부해 사유가 붙은 제외. 마커 수 차이 0242·0408은 기록만 | fixture를 다시 만들어 verified 규칙의 KLayout 판정이 golden과 같은지(reliability.py check) | `golden/drc-fixtures-20261128/golden.json` | 2026-11-28 |
| DRC 실제 칩 | KLayout 구현 규칙 96개 | Calibre v2023.4_17.10, 키트 DRC deck 무수정 | **일치** | v2 칩 1건(Cadence 제작), seal ring 없는 판·있는 판, 구현 규칙 범위 | seal ring 없음: KLayout 0 ↔ Calibre 0. seal ring 있음: KLayout 0 ↔ Calibre 1(1.PWL.bad1, KLayout 미구현 규칙) | PR마다 확인하지 않음. v2 GDS는 저장소 밖에 두고 기준점에서만 다시 대조 | `golden/chip-v2-20261128/summary.json`<br>미검증 `drc-unported-rules` | 2026-11-28 |
| LVS 코어 | KLayout 추출 + Netgen | Calibre LVS v2023.4_17.10, 키트 LVS deck 무수정 | **일치** | 오픈소스 흐름 코어 1건 | 같은 GDS(v_ternary8_top)·같은 schematic.spice에서 Netgen 일치, Calibre CORRECT(ports 15/15, nets 2096/2096, MOS 1895/1895) | 코어 LVS 일치는 ASIC gate가 PR마다 오픈소스로 확인. Calibre 대조는 기준점에서만 | `golden/chip-openflow-20261128/summary.json` | 2026-11-28 |
| LVS 칩·pad | KLayout 추출 + Netgen (칩 단위 미구현, 연결성 검사만) | Calibre LVS | **근거 없음(미검증)** | pad·GPIO를 포함한 칩 | v2 칩 Calibre CORRECT. 같은 칩 GDS의 오픈소스 LVS 없음. GPIO 원회로 CDL 확보, Calibre·오픈소스 대조 전 | 미검증 목록(asic-chip-lvs 미실행 허용) | `golden/chip-v2-20261128/summary.json`<br>미검증 `gpio-internal-lvs`<br>미검증 `lvs-vs-calibre` | 2026-11-28 |
| 합성 | Yosys | Genus | **근거 없음(미검증)** | - | Genus 325셀 결과 있음. 동치 미확인 | 미검증 목록 | 미검증 `synth-vs-genus` | 2026-11-28 |
| P&R·STA | OpenROAD + OpenSTA | Innovus + Tempus | **근거 없음(미검증)** | - | v2 코어 OpenSTA(SPEF) setup +38.4 / hold +1.41 ns. 같은 조건 비교 없음 | 미검증 목록(asic-chip-timing 미실행 허용) | 미검증 `pnr-sta-vs-innovus-tempus` | 2026-11-28 |
| PEX | OpenRCX | Quantus | **근거 없음(미검증)** | - | 없음. 현재 estimated.spef는 보정 전 전역 배선 추정 | 미검증 목록(asic-pex 미실행 허용) | 미검증 `pex` | 2026-11-28 |
| antenna | (미구현) | Calibre ANT, 키트 ANT deck 무수정 | **근거 없음(미검증)** | - | Calibre ANT 0건: 오픈소스 흐름 코어·SOP28 칩, v2 칩. KLayout antenna 구현과 fixture가 없어 대조 불가 | 미검증 목록 | `golden/chip-openflow-20261128/summary.json`<br>`golden/chip-v2-20261128/summary.json`<br>미검증 `antenna` | 2026-11-28 |
