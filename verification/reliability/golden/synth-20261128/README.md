# 합성 대조: RTL ↔ Genus netlist, RTL ↔ Yosys netlist (2026-11-28)

같은 RTL(5팀 main `ac5d641`, 수정 없음)로 Cadence Genus가 만든 netlist와 Yosys netlist가 RTL과 같은 기능인지 대조한 기록이다. 대응표(`../../table.json`)의 `synth` 칸 근거다.

- **기준점 1건이다.** 이 폴더는 RTL `ac5d641` 당시의 기록이다. RTL이 바뀌면 Genus 대조는 "기준점 당시 기록"으로 남는다. PR마다의 보증은 흐름 검사 `asic-synth-equiv`가 맡는다. 이 검사는 그 PR의 RTL과 CI가 만든 Yosys netlist를 같은 방법(아래)으로 대조하고, 실패하면 `run_asic --gate`가 실패한다.
- **판정은 오픈소스 형식 검증이다.** 판정은 Yosys `equiv_*`와 구조 검사(`scripts/asic/synth_equiv.py`)가 냈다. 상용 LEC(Conformal) 대조는 아직 없다. 다만 Genus가 독립적으로 합성한 netlist도 같은 검사를 통과했으므로, 이것이 오픈소스 판정을 교차 확인한다.
- Genus netlist 파일은 저장소에 넣지 않는다(v2 칩 GDS와 같은 원칙). 저장소 밖 근거 묶음에 두고 여기에는 sha256만 적는다. CI는 Genus 대조를 다시 하지 않는다.

## 1. 상용 출력 (Genus에서 옮긴 값)

| 항목 | 값 |
| --- | --- |
| 도구 | Genus `23.14-s090_1` |
| netlist | `v_ternary8_top.syn.v`, sha256 `6fef0f3e70eb4c857500e3d697cd0017ab54d4dc8481fc014e9997bc3600ed24` |
| 셀·flop·면적 | 325셀, flop 64, 196,992 µm² (`report_gates` 그대로, 종류별 수는 `summary.json` `commercial`) |
| 설정 | `read_hdl -language v2001`, `syn_generic`·`syn_map`·`syn_opt` effort medium, `ungroup -all -flatten`, `dont_use` LATCHX1·TBUFX1·TBUFX2, 키트 Liberty 무수정 |

## 2. 오픈소스 판정 기록 (로컬 실행)

입력: RTL `src/` 10개 파일(해시는 `summary.json` `meta.rtl_sha256`), 키트 Liberty `0c84f0d9…`(셀 동작), 키트 Verilog 셀 모델 `846c7085…`(셀 모델 대조에만 씀). Yosys netlist는 두 개를 대조했다. 하나는 CI와 같은 Ubuntu apt Yosys 0.33으로 만든 것(437셀, `dc328929…`)이고, 다른 하나는 로컬 Yosys 0.68+40 흐름의 `synth/netlist.v`(452셀, `29e667e2…`, P&R 결과 `final.v`는 `../sta-20261128/`의 netlist와 같음)다. 두 수치는 이 실행의 값이고, CI 출력과 맞춰 보는 기대값이 아니다.

`python scripts/asic/synth_equiv.py --netlist <netlist> --liberty <키트 Liberty> --out <새 폴더> [--synth-log <Yosys 합성 로그>] --cell-models <키트 Verilog 모델>`

검사는 네 부분이다. 넷 다 통과해야 한다.

| 부분 | 종류 | 내용 |
| --- | --- | --- |
| 포트 | 구조 검사 | RTL과 gate의 포트 이름·방향·폭이 같다. P&R이 넣는 inout 전원 핀만 예외다 |
| 클록 | 구조 검사 | RTL 레지스터는 모두 클록 포트의 상승 에지 flop이고 비동기 set/reset이 없다. gate flop은 모두 Liberty ff가 상승 에지이고 clear/preset이 없으며, 클록 핀이 클록 포트에 바로 연결된다. 아래 형식 증명의 SAT 모델은 flop을 "매 주기 Q←D"로만 보고 클록 핀을 보지 않으므로 따로 검사한다 |
| 다음 상태 함수 | 형식 증명 | `equiv_make`로 같은 이름의 신호끼리 짝짓고, `equiv_simple -seq 5`·`equiv_induct -seq 5`로 모든 짝을 증명한다(`equiv_status -assert`). 셀은 Liberty function이다. Genus는 flop 인스턴스 이름(`\u_weights_WEIGHTS_reg[2]`)으로 RTL 이름 별칭 wire를 붙인다(셀 변경 없음). Yosys의 one-hot FSM 재부호화(`00 → ---1`, `10 → --1-`, `01 → -1--`, `11 → 1---`)는 합성 로그 표를 `equiv_make -encfile`로 준다 |
| 리셋 뒤 출발 조건 | 형식 검사(유계) | 초기 상태를 자유로 두고 1주기에 `RST_N=0`을 준다. 2~8주기에 모든 짝이 같아야 한다(`equiv_miter` + `sat`). 위 귀납 증명의 출발 조건이다 |

| 대조 | 포트 | 클록 | 다음 상태 | 출발 조건 | 비고 |
| --- | --- | --- | --- | --- | --- |
| RTL ↔ Genus | 같음 | 통과(flop 64) | 109/109 증명 | 통과 | `result_shift[15:13]`은 RTL에서 항상 0이라 Genus가 지웠다. 이 세 비트 없이 증명됐다 |
| RTL ↔ Yosys(CI형 0.33) | 같음 | 통과(flop 66) | 72/72 증명 | 통과 | 같은 세 비트를 Yosys도 지웠다 |
| RTL ↔ Yosys(로컬 0.68+40) | 같음 | 통과(flop 66) | 72/72 증명 | 통과 | FSM 부호표 없이 돌리면 70짝 중 14짝만 증명된다 |

검사기는 Yosys 0.33과 0.68+40에서 같은 결과를 냈다.

틀린 netlist를 놓치지 않는지 일부러 고친 사본 17개로 확인했다. 모두 실패했다(`summary.json` `negative_controls`).

- 한 셀 바꿈 4개, 틀린 FSM 표 1개 → 다음 상태 증명 실패
- 음에지 flop, `IN_VALID`·`RST_N`으로 클록된 flop, 비동기 set flop → 클록 검사 실패
- 포트 목록에서 `OUT_VALID` 삭제·이름 변경 → 포트 검사 실패
- 출력 상수화, 출력 비트 맞바꿈 → 다음 상태 증명 실패
- 리셋값 변경 3개 → 다음 상태 증명과 출발 조건 모두 실패

셀 모델: 두 netlist가 쓰는 조합 셀 16종은 키트 Verilog 모델과 Liberty function이 같다(셀마다 형식 증명). DFFPOSX1은 대조하지 않았다. 키트 Verilog 모델이 하강 에지에 D를 받아 상승 에지에 내보내는 2-에지 모델이기 때문이다. 대신 Liberty ff(상승 에지)를 썼다. Liberty ff가 실제 셀과 같다는 근거는 이 폴더에 없다.

### 시험 (형식 증명이 아님)

같은 팀 시험을 RTL·Genus netlist·로컬 Yosys netlist에 돌렸다. 시험은 `scripts/run_rtl.py`의 integration·regression 그룹이다(`tests/rtl/test_top.py` 6개 시험, seed 20261112, Icarus, 셀은 Liberty function 모델). 셋 다 통과했고, 각 42,907작업이다.

기록만: MyChip PDK 검사의 OpenSTA(100 ns, 지연 ×1.5/×0.7)로 본 Genus netlist는 setup +41.153 / hold +1.365 ns다(SDC 2행 변경 전후 같음).

## 이 결과로 말할 수 있는 것과 없는 것

- RTL `ac5d641`에서 Genus와 Yosys가 만든 netlist는 둘 다 RTL과 기능이 같다. 근거는 오픈소스 형식 검증과 구조 검사이며, 기준점 1건이다. 같은 시험도 모두 통과한다.
- RTL이 바뀐 뒤의 Yosys netlist는 `asic-synth-equiv`가 PR마다 같은 방법으로 본다. Genus netlist는 다시 보지 않는다. 제출 직전 기준점에서 같은 RTL로 Genus를 다시 돌려 대조한다(`../../CHECKPOINT.md`).
- 상용 판정(Conformal LEC)은 없다. 다음 서버 묶음 후보다.
- P&R 뒤 netlist(`final.v`)는 이 형식 검사에 넣지 않았다. OpenROAD가 일부 net 이름을 바꿔 이름 짝짓기가 모자라기 때문이다. P&R 뒤 netlist는 ASIC gate가 PR마다 같은 팀 시험으로 확인한다(`asic-gate`).
- 타이밍·면적은 비교하지 않는다(도구마다 셀 선택이 다르다).

도구 판: Genus `23.14-s090_1`, Yosys `0.33`·`0.68+40`, Icarus Verilog 14.0(devel), cocotb 2.0.1. 서버 이름·주소·계정·경로와 원본 로그는 공개 저장소에 넣지 않는다(SPEC 0019).
