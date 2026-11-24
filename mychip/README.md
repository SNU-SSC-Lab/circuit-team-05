# mychip/ — RTL 다음 단계 산출물

합성·배치배선·사인오프 결과는 **이 폴더의 정해진 자리**에 둡니다. 이 저장소는 **`MyChip PDK`** 체크(`.github/workflows/pdk.yml`, 코드 `scripts/run_pdk.py`, 기준 `verification/pdk/`)가 PR마다 이 폴더를 단계별로 자동 검사합니다. 아직 안 한 단계는 ⬜로 표시되고 실패가 아닙니다. 올라온 단계는 맞아야 통과합니다. 칩끼리의 연결 계약은 `MyChip integration` 체크가 따로 봅니다.

이 칩의 top: **`v_ternary8_top`** (아래 `<top>` 자리에 그대로 씁니다)

```
mychip/
├─ constraints/<top>.sdc        합성에 쓴 타이밍 제약
├─ 1-synth/<top>.v              합성 netlist (Genus)
│         reports/*.rpt         area · timing · qor
├─ 2-pnr/<top>.v                배치·배선 후 netlist (전원 핀 없이)
│        <top>.spef             배선 기생 성분 (있으면 타이밍에 반영)
│        reports/*.rpt
└─ 3-signoff/drc.rpt            Calibre 또는 Assura DRC 요약
             lvs.rpt            Calibre 또는 Assura LVS 결과
             <top>.gds.sha256   최종 GDS의 SHA-256 (GDS 파일은 올리지 않음)
```

## 단계별로 무엇을 검사하나

| 단계 | 올리는 것 | PDK 검사가 하는 일 |
| --- | --- | --- |
| RTL (지금) | RTL | 4차 PDK로 직접 합성 → 합성 netlist에 팀 top 시험(`tests/rtl/test_top.py`) → 10 MHz 타이밍 (칩 간 연결은 통합 검사) |
| 1-synth | Genus netlist, SDC, 리포트 | **팀 netlist**에 같은 팀 top 시험, 같은 타이밍 검사. SDC 클록이 100 ns보다 느리면 실패 |
| 2-pnr | 배선 후 netlist, SPEF, 리포트 | 위와 같고, SPEF가 있으면 실제 배선 지연으로 타이밍 |
| 3-signoff | DRC·LVS 리포트, GDS 해시 | DRC 0건, LVS 일치, 두 리포트가 이 칩 top을 가리키는지, 해시 형식 |

DRC·LVS 자체는 학교 서버의 Calibre/Assura로 돌리고(안내서 p. 8: 공식 deck만 인정), 결과 리포트로 판정합니다.

## 만드는 법 (예)

```tcl
# Genus
write_hdl > mychip/1-synth/v_ternary8_top.v
write_sdc > mychip/constraints/v_ternary8_top.sdc
report_area   > mychip/1-synth/reports/area.rpt
report_timing > mychip/1-synth/reports/timing.rpt
report_qor    > mychip/1-synth/reports/qor.rpt

# Innovus (전원 핀 없는 netlist)
saveNetlist mychip/2-pnr/v_ternary8_top.v
rcOut -spef mychip/2-pnr/v_ternary8_top.spef
```

```bash
# 최종 GDS의 해시 (GDS는 학교 서버에 두고 해시만 올림)
sha256sum v_ternary8_top.gds > mychip/3-signoff/v_ternary8_top.gds.sha256
```

Calibre는 DRC summary 파일을 `drc.rpt`로, LVS report를 `lvs.rpt`로 복사합니다. Assura는 DRC 요약과 LVS 결과(`Schematic and Layout Match`가 나오는 파일)를 같은 이름으로 둡니다.

## 올리면 안 되는 것

이 폴더에는 `.v .sdc .sdf .spef .rpt .txt .sha256 .md`만 들어갑니다. GDS·OASIS, Cadence 라이브러리·DB, 로그 덩어리는 `.gitignore`가 막고 CI도 실패시킵니다. PDK 파일은 이미 공개돼 있어 다시 올릴 필요가 없습니다.
