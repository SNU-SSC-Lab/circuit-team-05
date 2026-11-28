# 오픈소스 흐름 출력의 Calibre 검사 (2026-11-28)

오픈소스 흐름(`python scripts/run_asic.py --target chip`)이 만든 코어 `v_ternary8_top`와 SOP28 칩 `ternary8_sop28` GDS를 상용 도구 Calibre로 DRC·ANT·LVS 검사한 결과와, 같은 GDS에 KLayout 구현 규칙 96개를 돌린 결과 요약이다. 대응표(`../../table.json`)의 `drc-chip-openflow`·`lvs-core` 칸 근거이고, `antenna` 칸의 참고 기록이다(SPEC 0019 2절). `summary.json`의 Calibre 값은 Calibre 보고서에서 옮겨 적었고, 손으로 판정을 고치지 않는다. GDS와 Calibre 원본 보고서·로그는 저장소에 넣지 않는다.

## 실행 조건

| 항목 | 값 |
| --- | --- |
| 실행일 | 2026-11-28 |
| 도구 | Calibre `v2023.4_17.10` |
| PDK | 공개 tarball `NSPL_05CMOS_PDK_260820.tar.gz` sha256 `2e49115a08f6af96c1f8433130ad4316551b5eba9001a3133905b544166af954` |
| DRC deck | 키트 `Calibre/DRC/NSPL_0p5um_Analog_CMOS_2P3M_5V_V1.1_DRC.cal` 무수정, sha256 `6c01207311236d148dc183576fa8f5156e1a21d40a19609322c810fa919c4f0f`, RULECHECK 209개 |
| ANT deck | 키트 `Calibre/ANT/NSPL_0p5um_Analog_CMOS_2P3M_5V_V1.1_ANT.cal` 무수정, sha256 `80dc257e6778121ab9a61a444d0e82c79999dc785d8e6aa5a6a2a5318c7b94b5`, RULECHECK 12개 |
| LVS deck | 키트 `Calibre/LVS/NSPL_0p5um_Analog_CMOS_2P3M_5V_V1.1_LVS.cal` 무수정, sha256 `4cebfddc77ab6b4fb20e869281a895be9933a900670c98ff792ed5204c6366e0` |
| header | 키트 `drc_header.cal`·`ant_header.cal`·`lvs_header.cal`에서 최상위 셀 이름만 바꿈. DRC 결과 수 제한 없음(`DRC MAXIMUM RESULTS ALL`) |
| 실행 방식 | DRC·ANT는 `calibre -drc -hier`, LVS는 `calibre -lvs -hier -spice` |
| KLayout DRC | KLayout `0.28.16`, `scripts/asic/drc_audit.py` 확장 profile(구현 규칙 96개), 같은 날 같은 GDS |
| LVS source | 오픈소스 흐름의 `schematic.spice`(sha256 `da41de1caf9ee1e08e06fb0fc9fafdc3c4dd64dfd014eb1efb3da7e92f57064c`)와 `cells.spice`(sha256 `281efca41e93e7f88cf59e18e64159f9772111cfee1f86647cbd6ac3703e9f11`). 오픈소스 Netgen LVS가 쓴 것과 같은 파일 |

## 입력 GDS

| 설계 | 뜻 | sha256 |
| --- | --- | --- |
| `v_ternary8_top` | 코어 | `fa6ab910b7f03fd4c966c9c19b2455fd7f26297614c1f20ccb221fed9b09ea93` |
| `ternary8_sop28` | SOP28 칩(검토 전 제안 핀맵) | `967bcad67c0f3a4df18e2faec2c10df65c33b27f6da0fef8794ce6168c550fdb` |

## 결과

| 설계 | Calibre DRC | Calibre ANT | Calibre LVS | 오픈소스 쪽 같은 GDS 결과 |
| --- | --- | --- | --- | --- |
| `v_ternary8_top` | 0건 | 0건 | CORRECT (ports 15/15, nets 2096/2096, MOS 1895/1895) | Netgen LVS 일치, KLayout 구현 규칙 96개 DRC 0건 |
| `ternary8_sop28` | 0건 | 0건 | 실행하지 않음 | KLayout 구현 규칙 96개 DRC 0건 |

- 코어 LVS는 같은 GDS·같은 source netlist로 오픈소스(KLayout 추출 + Netgen)와 Calibre가 모두 일치를 냈다. 대응표에서 범위 "오픈소스 흐름 코어 1건"의 일치 근거로 쓴다. pad를 포함한 칩 LVS는 미검증 목록 `gpio-internal-lvs`·`lvs-vs-calibre`에 남는다.
- DRC는 두 GDS 모두 KLayout 구현 규칙 96개 0건 ↔ Calibre 0건이다. 대응표에서 범위 "오픈소스 흐름 코어·SOP28 칩 2건, 구현 규칙 범위"의 일치 근거로 쓴다. 옮기지 않은 113개 규칙은 KLayout 판정이 없으므로 미검증 목록 `drc-unported-rules`에 남는다.
- antenna는 KLayout 쪽 구현이 없어 Calibre ANT 0건은 상용 기준의 기록일 뿐 도구 대조 근거가 아니다.

서버 이름·주소·계정·경로와 원본 로그는 공개 저장소에 넣지 않는다(SPEC 0019).
