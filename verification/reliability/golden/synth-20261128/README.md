# 합성 대조: RTL ↔ Genus netlist, RTL ↔ Yosys netlist (2026-11-28)

같은 RTL(5팀 main `ac5d641`, 수정 없음)로 Cadence Genus가 만든 netlist와 오픈소스 흐름의 Yosys netlist가 RTL과 같은 기능인지 대조한 결과다. 대응표(`../../table.json`)의 `synth` 칸 근거다. 기준점 1건이고, PR마다 다시 하지 않는다.

Genus netlist 파일은 저장소에 넣지 않는다(v2 칩 GDS와 같은 원칙). 저장소 밖 근거 묶음에 두고 여기에는 sha256만 적는다. CI는 이 대조를 다시 하지 않으므로 그 파일 없이도 통과한다. `summary.json`의 Genus 셀 수·면적·종류별 수는 Genus `report_gates` 그대로이고, 대조 결과는 같은 날 로컬(WSL)에서 실행한 값이다.

## 입력

| 입력 | 내용 | sha256 |
| --- | --- | --- |
| RTL | `src/` 10개 파일, `ac5d641` = main `e6acdd6`의 `src/` | 파일별 해시는 `summary.json` `meta.rtl_sha256` |
| Genus netlist | Genus `23.14-s090_1`, `v_ternary8_top.syn.v`, 셀 325개(flop 64), 면적 196,992 µm² | `6fef0f3e70eb4c857500e3d697cd0017ab54d4dc8481fc014e9997bc3600ed24` |
| Yosys netlist | 흐름의 `synth/netlist.v`(main `e6acdd6`, Yosys 0.68+40), 셀 452개(flop 66) | `29e667e21a1b3527ba4745f2685a1e6fae065fdd4db8b01b786605bc787b0490` |
| 셀 동작 | 키트 Liberty `..._12T_std_tt.lib`의 function·ff | `0c84f0d970d374ba5c9c4cf7aec22fec96e306f8be373bda9ef20ce2bb48de51` |
| 키트 Verilog 셀 모델 | `..._12T_std.v` (셀 모델 대조에만 씀) | `846c7085348384851c9f787caf17635e6e3633ddb8014ce0b71dbf8fbb05f0b5` |

Genus 설정: `read_hdl -language v2001`, `syn_generic`·`syn_map`·`syn_opt` effort medium, `ungroup -all -flatten`, `dont_use` LATCHX1·TBUFX1·TBUFX2, 키트 Liberty 무수정. Yosys netlist의 P&R 결과(`pnr/final.v`, `1ffd0df6…`)는 `../sta-20261128/`의 netlist와 같다.

## 형식 증명

`python scripts/asic/synth_equiv.py --netlist <netlist> --liberty <키트 Liberty> --out <새 폴더> [--synth-log <Yosys 합성 로그>] --cell-models <키트 Verilog 모델>`

- RTL(gold)과 netlist(gate)를 Yosys `equiv_make`로 같은 이름의 신호끼리 짝짓고, `equiv_simple -seq 5`, `equiv_induct -seq 5`로 모든 짝을 증명한다. 하나라도 남으면 실패다(`equiv_status -assert`). 출력 포트는 모두 짝이 된다.
- 셀은 키트 Liberty의 function·ff로 본다(PR마다 도는 게이트 수준 시험 `pdk.gate_model`과 같은 모델).
- 레지스터 대응: Genus는 flop 인스턴스 이름(`\u_weights_WEIGHTS_reg[2]`)에 RTL 이름이 있고 출력 net 이름은 제각각이다(`\u_weights_WEIGHTS[2]_108`, `term_negate`). 검사용 사본에 RTL 이름의 별칭 wire를 붙인다(64개, 셀은 바꾸지 않음). Yosys는 flop 출력이 RTL 이름을 그대로 가진다.
- Yosys는 제어기 상태 레지스터를 one-hot으로 바꿨다(2비트 → 4비트: `00 → ---1`, `10 → --1-`, `01 → -1--`, `11 → 1---`). 합성 로그의 이 표를 `equiv_make -encfile`로 준다. 표 없이 돌리면 70짝 중 14짝만 증명되어 실패한다.
- 가정: 짝지은 레지스터가 같은 값에서 시작한다. 모든 레지스터에 동기 리셋이 있어 리셋 한 주기 뒤에 성립한다.

| 대조 | 결과 | 짝 | 비고 |
| --- | --- | --- | --- |
| RTL ↔ Genus | 같음 | 109 / 109 증명 | `result_shift[15:13]`은 RTL에서 항상 0이라 Genus가 지웠다. 이 세 비트 없이 증명됐다 |
| RTL ↔ Yosys | 같음 | 72 / 72 증명 | 같은 세 비트를 Yosys도 지웠다. FSM 부호표 사용 |

검사가 틀린 netlist를 놓치지 않는지 일부러 고친 사본으로 확인했다. 모두 실패했다: Genus 첫 NAND2X1 → AND2X1(0/109), 첫 OAI21X1 → AOI21X1(106/109), Yosys 첫 XOR2X1 → XNOR2X1(44/72), 첫 NAND2X1 → OR2X1(45/72), FSM 부호 `10`·`01` 맞바꿈(15/72).

셀 모델: 두 netlist가 쓰는 조합 셀 16종은 키트 Verilog 모델과 Liberty function이 같다(셀마다 형식 증명). DFFPOSX1의 키트 Verilog 모델은 하강 에지에 D를 받아 상승 에지에 내보내는 2-에지 모델이라 대조하지 않고 Liberty ff(상승 에지)를 썼다.

## 시험 (형식 증명이 아님)

같은 팀 시험을 RTL과 두 netlist에 돌렸다: `scripts/run_rtl.py`의 integration·regression 그룹(`tests/rtl/test_top.py` 6개 시험, seed 20261112, Icarus). netlist는 Liberty function 모델로 바꿔 돌렸다(`pdk.gate_level`, 단계 `full`).

| 대상 | 결과 | 결과 확인 작업 수 |
| --- | --- | --- |
| RTL | 통과 | 42,907 |
| Genus netlist | 통과 | 42,907 |
| Yosys netlist | 통과 | 42,907 |

기록만: MyChip PDK 검사의 OpenSTA(100 ns, 지연 ×1.5/×0.7)로 본 Genus netlist는 setup +41.153 / hold +1.365 ns다(SDC 2행 변경 전후 같음).

## 이 결과로 말할 수 있는 것과 없는 것

- 같은 RTL에서 Genus와 Yosys가 만든 netlist는 둘 다 RTL과 기능이 같다(형식 증명, 기준점 1건). 같은 시험도 모두 통과한다.
- RTL이 바뀌면 이 결과는 그 RTL에 대해 말하지 않는다. 다시 받으려면 같은 RTL로 Genus를 돌리고 위 명령으로 대조한다(`../../CHECKPOINT.md`).
- P&R 뒤 netlist(`final.v`)는 이 형식 증명에 넣지 않았다. OpenROAD가 일부 net 이름을 바꿔 이름 짝짓기가 모자란다. P&R 뒤 netlist는 ASIC gate가 PR마다 같은 팀 시험으로 확인한다(`asic-gate`).
- 타이밍·면적은 비교하지 않는다(도구마다 셀 선택이 다르다).

도구 판: Genus `23.14-s090_1`, Yosys `0.68+40`(대조와 Yosys netlist 모두), Icarus Verilog 14.0(devel), cocotb 2.0.1. 서버 이름·주소·계정·경로와 원본 로그는 공개 저장소에 넣지 않는다(SPEC 0019).
