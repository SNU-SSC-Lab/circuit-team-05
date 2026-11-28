# 5팀 DRC·LVS 사용 방법과 R&D 맥락

성준님 공유용 · 실행 근거 2026-11-24 · 맥락 보완 2026-11-27 · PR #11 작업 브랜치 기준

**전체 칩의 제출용 검증은 아직 미완료다.** 실제 NSPL 검사는 KLayout으로 도형 검사·소자 추출을 하고 Netgen으로 회로를 비교한다. 처음 공유한 Magic 경로는 별도의 `scmos` 연습 시험에 남아 있다.

| 구분 | 확인한 범위 | 남은 일 |
| --- | --- | --- |
| DRC | 원본 활성 209개 대조, 구현한 기하 검사 113개에서 코어·패드 포함 GDS 오류 0건. DRC 도형 시험 679개 통과, 113개 규칙의 판정이 Calibre golden과 일치(2026-11-28, `verification/reliability/`, 금속·via·PAD 17개는 SPEC 0021). 키트 ANT deck 12개 검사도 옮겨 fixture 102개가 Calibre와 일치, 코어·칩 0건(SPEC 0020) | 96개 규칙·전역 입력 플래그 이식 |
| LVS | 내적 코어의 실제 GDS 추출 회로와 독립 기준 CDL 일치 | GPIO·ESD를 포함한 전체 칩 LVS |
| 기능 | 최종 netlist의 6개 시험·42,907작업 회귀 통과 | 실제 제작 칩·보드 시험 |
| RC·PEX | 추정 배선 RC와 탐색용 SPEF 생성 | 공정에 맞춘 RC 모델·정밀 추출·정확도 대조 |

1~8절은 실행 방법, 9~12절은 전체 검증 CI를 완성하지 못한 경위와 R&D를 이어갈 지점이다. 아래 실측은 11월 24일 로컬 기록이며 이번 문서 보완에서 ASIC 전체를 다시 실행한 결과는 아니다.

## 1. 코드 받기

Ubuntu 24.04 x86_64 또는 WSL Ubuntu의 새 폴더 기준이다. 비공개 저장소 접근 권한이 있는 GitHub 계정으로 인증한다. 기존 작업 폴더에 덮어쓰지 않는다. 현재 실행기는 저장소·PDK·결과 경로에 공백이 없어야 한다.

```bash
git clone --branch feat/nspl-drc-rule-tests --single-branch https://github.com/SNU-SSC-Lab/circuit-team-05.git circuit-team-05-drc
cd circuit-team-05-drc
export TEAM05_REPO="$PWD"
```

현재 구현은 [PR #10](https://github.com/SNU-SSC-Lab/circuit-team-05/pull/10) 위에 [PR #11](https://github.com/SNU-SSC-Lab/circuit-team-05/pull/11)을 쌓은 상태다. main의 코드만 받으면 아래 명령이 없을 수 있다. 두 PR 병합 후에는 main의 같은 파일을 기준으로 실행한다.

## 2. 도구와 PDK 준비

```bash
sudo apt-get update
sudo apt-get install -y git python3-venv yosys iverilog klayout netgen-lvs libtcl8.6 libgomp1 libqt5widgets5 libqt5gui5 libqt5network5 libqt5printsupport5 time
python3 -m venv "$HOME/.venvs/team05-asic"
. "$HOME/.venvs/team05-asic/bin/activate"
python -m pip install --index-url https://pypi.org/simple -r requirements-ci.txt
python scripts/asic/setup_tools.py --out "$HOME/ssc-asic-tools"
python scripts/asic/fetch_pdk.py --out "$HOME/ssc-asic-pdk"
export TEAM05_PDK="$HOME/ssc-asic-pdk/NSPL_05CMOS_PDK_260820"
export TEAM05_TOOLS="$HOME/ssc-asic-tools/bin"
```

다운로드한 OpenROAD·PDK는 고정 해시를 확인한다. PDK 원본은 수정하거나 Git에 올리지 않는다. 회로 비교 패키지 이름은 `netgen-lvs`이며 같은 이름의 격자 생성 도구와 구분한다.

## 3. 실제 칩 생성 전, 검사기가 오류를 잡는지 확인

```bash
python scripts/asic/drc_catalog.py --pdk "$TEAM05_PDK" --out "$HOME/ssc-team05-runs/catalog-01"
python scripts/asic/drc_selftest.py --out "$HOME/ssc-team05-runs/drc-tests-01"
```

첫 명령은 원본 활성 209개 검사와 목록이 같은지 확인한다. 두 번째는 GDS로 저장·재반입한 정상/위반·수치 경계·계층 도형 451개를 시험한다. `selftest.json`의 `status: pass`는 **정상 도형을 통과시키고 의도한 오류를 잡았다는 뜻**이다. Calibre와의 대조는 이 명령이 아니라 `python scripts/asic/reliability.py check --selftest 그폴더/selftest.json --out 새폴더`가 한다. 2026-11-28 Calibre golden(`verification/reliability/golden/drc-fixtures-20261128/`, `…20261128b/`)과 비교해 451개 중 449개가 대상 규칙 발동 여부가 같고, 2개(0169·0170)는 Calibre가 입력을 거부해 사유가 붙은 제외다. `selftest.json`의 `rule_states`는 `verification/asic/drc-rules.json`이 정한 규칙 상태 수(지금 `verified` 96개)다.

재실행할 때는 `-02`처럼 새 출력 폴더를 지정한다. 실행기는 이전 결과를 덮어쓰지 않는다.

## 4. 우리 코어 생성·LVS·기능 시험 재현

```bash
export TEAM05_OUT="$HOME/ssc-team05-runs/core-01"
python scripts/run_asic.py --pdk "$TEAM05_PDK" --openroad "$TEAM05_TOOLS/openroad" --target core --experimental --out "$TEAM05_OUT"
python -m json.tool "$TEAM05_OUT/result.json"
```

합성 → 배치·클록 트리·전원망·배선 → 실제 셀 GDS 병합 → GDS 소자 추출 → Netgen LVS → 최종 netlist 기능 회귀 순서다. 로컬 전체 실행은 약 3~4분대였지만 PC·도구 버전에 따라 달라진다.

실험 재현을 위해 `--experimental`을 명시했다. 지정된 미확인 공정 항목 외의 필수 검사를 실행·통과해야 종료 코드 0을 허용한다. JSON의 전체 `status: incomplete`와 `ready_for_submission: false`는 유지한다. 옵션을 빼면 현재는 끝까지 산출물을 만들어도 미확인 항목 때문에 1로 종료한다. 실제 LVS 불일치나 미실행을 성공으로 바꾸는 옵션은 아니다. PR 머지 게이트(`asic-gate`)는 `--target chip --gate`로 실행하며 미검증 목록 `verification/reliability/unverified.json`의 `allows_checks`만 허용한다(SPEC 0019).

| 파일·항목 | 읽는 방법 |
| --- | --- |
| `report.html` / `summary.md` | 검사 상태·시간·그림부터 확인. HTML은 폴더 전체를 유지해 열기 |
| `result.json` → `checks.asic-lvs.status` | 코어 LVS의 최종 판정. 도구 종료 코드와 구분 |
| `lvs/layout.spice` | 실제 GDS에서 추출한 소자·연결 |
| `lvs/schematic.spice` + `cells.spice` | 최종 netlist와 원본 셀 CDL로 만든 독립 기준 회로 |
| `lvs/lvs.log`, `lvs.json` | 핀·연결·W/L 비교 근거. 성공 문구 하나만 보고 판단하지 않기 |
| `pnr/final.v`, `v_ternary8_top.gds` | 같은 실행의 최종 netlist·코어 GDS |
| `pnr/estimated.spef` | 보정 전 전역 배선 추정값. 정밀 PEX 결과가 아님 |

## 5. 생성한 GDS에 확장 DRC 96개 적용

```bash
python scripts/asic/drc_audit.py --pdk "$TEAM05_PDK" --gds "$TEAM05_OUT/v_ternary8_top.gds" --top v_ternary8_top --out "$TEAM05_OUT/drc-expanded"
python -m json.tool "$TEAM05_OUT/drc-expanded/result.json"
```

`geometry.json`에 규칙별 마커 수와 처음 30개 오류 좌표가 있다. `rules.md`에는 미구현 항목이 있다. 오류 0건이어도 `incomplete`, `qualified_process_drc: false`다. 이 명령의 종료 코드 0은 구현된 기하 검사에 오류가 없다는 뜻이다.

전체 제안 조립본도 보려면 4절 명령에서 `--target chip`과 **다른 출력 폴더**를 사용한다. 확장 DRC 입력은 그 폴더의 `ternary8_sop28.gds`, top은 `ternary8_sop28`로 바꾼다. 전체 GPIO/ESD LVS·최종 핀맵 승인은 여전히 미완료다.

## 6. Netgen 비교만 따로 다시 실행

4절이 끝난 뒤 같은 입력을 새 폴더에 복사해 비교 단계를 재현할 수 있다. 기준 회로의 include 파일도 함께 복사한다. 자동 실행처럼 Netgen 전에 두 netlist를 `lvs_reduce.py`로 줄인다(키트 deck의 병렬 MOS 합치기·직렬 입력 순서·split gate와 같은 의미).

```bash
export TEAM05_LVS_RECHECK="$TEAM05_OUT/lvs-recheck-01"
mkdir "$TEAM05_LVS_RECHECK"
cp "$TEAM05_OUT/lvs/"{layout.spice,schematic.spice,cells.spice,run.tcl} "$TEAM05_LVS_RECHECK/"
(
  cd "$TEAM05_LVS_RECHECK"
  python "$TEAM05_REPO/scripts/asic/lvs_reduce.py" layout.spice layout.reduced.spice
  python "$TEAM05_REPO/scripts/asic/lvs_reduce.py" schematic.spice schematic.reduced.spice
  export SSC_TOP=v_ternary8_top
  export SSC_EXTRACTED="$TEAM05_LVS_RECHECK/layout.reduced.spice"
  export SSC_SCHEMATIC="$TEAM05_LVS_RECHECK/schematic.reduced.spice"
  export SSC_SETUP="$TEAM05_REPO/verification/asic/netgen_setup.tcl"
  netgen-lvs -batch source run.tcl
)
```

새 `lvs.log`·`lvs.json`을 확인한다. `netgen-complete.txt`는 명령 완료 표시이며 회로 일치 표시가 아니다. 최종 판정은 완료 표시·보고서·JSON의 핀/연결/소자 속성을 함께 확인해야 한다. 소스 설치 환경에서 실행 파일이 `netgen`이면 마지막 명령의 이름만 해당 실행 파일로 바꾼다.

자동 실행과 같은 판정기를 사용하려면 다음을 실행한다. 위에서 켠 Python 환경을 그대로 사용한다.

```bash
python - <<'PY'
import json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(os.environ['TEAM05_REPO']) / 'scripts'))
from run_physical import lvs_verdict
folder = Path(os.environ['TEAM05_LVS_RECHECK'])
matched = (folder / 'netgen-complete.txt').is_file() and lvs_verdict(
    (folder / 'lvs.log').read_text(),
    json.loads((folder / 'lvs.json').read_text()), 'v_ternary8_top')
print('Core LVS PASS' if matched else 'Core LVS FAIL')
raise SystemExit(0 if matched else 1)
PY
```

## 7. Magic을 직접 연습하려면

```bash
sudo apt-get install -y magic
python scripts/run_physical.py selftest --out "$HOME/ssc-team05-runs/magic-practice-01"
python scripts/run_physical.py report --result "$HOME/ssc-team05-runs/magic-practice-01/result.json"
```

내장 `scmos` 연습 회로의 6개 시험이며 NSPL 칩 검사가 아니다. 설치·DRC·추출·Netgen·PEX 학습 명령은 [Magic·Netgen 상세 사용서](magic-netgen-guide.md)에 있다. 공개 Magic 기술파일을 현재 NSPL에 그대로 적용해 정확한 PEX를 검증한 상태는 아니다.

## 8. PEX 방법을 함께 확인할 때

성준님이 알고 있는 방법의 **실행 도구·버전, 공정 설정, 명령, 작은 입력 GDS와 출력 예제**를 기준으로 대조한다. 다른 공정에서 실행됐다는 사실과 NSPL 260820의 정확도는 구분한다.

- Magic 경로라면 사용한 `.tech/.magicrc`, R 추출 포함 여부, 결과 SPICE의 단위·소자/노드 대응을 확인한다.
- SPEF 경로라면 RC 규칙·corner·단위와 최종 netlist의 net 대응을 확인한다. SPICE 파일의 확장자만 SPEF로 바꾸어 사용하지 않는다.
- 키트에는 RC 단면·QRC 패턴/모델 자료가 있다. 어느 자료를 어떤 조건으로 사용했는지 남기고 같은 입력의 기준 결과와 비교한다.

## 9. 왜 전체 검증 CI를 완성하지 못했나

**로컬 구현은 실행됐지만 공정 전체 검증을 입증하지 못했고, GitHub에서는 실행기 할당도 막혔다.** 이 둘은 별도로 해결해야 한다. YAML에 명령을 더 연결하는 것만으로 남은 공정 검증이 완성되지는 않는다.

초기에는 목표 범위를 충분히 맞추지 못했다. 먼저 만든 것은 외부에서 받은 GDS·설정으로 검사를 실행할 틀과 Magic `scmos` 연습 회로의 자체 시험이었다. 원했던 것은 우리 RTL에서 합성·P&R·GDS 생성까지 직접 수행하고 검사·리포트를 받는 흐름이었다. 따라서 초기 `Physical checks`의 성공을 우리 NSPL 칩의 물리 검증 성공으로 읽을 수 없었다. 이후 SPEC 0017과 PR #10에서 실제 구현 흐름을 추가했다.

그다음에는 NSPL 키트와 각 오픈소스 도구 사이의 설정·추출·규칙 변환을 직접 맞춰야 했다. 키트에는 LEF·GDS·CDL·RC 자료가 있지만, 이를 현재 도구에 넣기만 하면 전체 공정 검증이 끝나는 상태는 아니었다. 코어 구현에서 발견한 오류는 고쳤고, 아직 정확도를 확인하지 못한 검사에는 `unsupported`를 남겼다.

| 구분 | 확인한 사실 | 의미 |
| --- | --- | --- |
| 로컬 구현·검사 | Ubuntu 호환 실행 256.202초. 코어 3,892 MOS LVS 일치, 최종 netlist 6개 시험·42,907작업 통과 | 실제 코어 생성과 검사 경로는 동작했다. 전체 칩 제출 검증의 증거는 아님 |
| 전체 공정 판정 | PEX·전체 DRC·GPIO LVS/타이밍·핀맵 미확인 | 기본 strict 실행은 산출물을 만들어도 실패로 종료한다. `incomplete`는 의도한 판정 |
| GitHub 실행 | 문서 작성 전 확인한 11월 24일 실행은 실행기 이름이 비어 있고 실행된 step이 0개 | 원격 도구 실행·시간·메모리·성공 여부를 판단할 수 없음 |

11월 27일 문서 작성 전에 조회한 [11월 24일 ASIC 실행](https://github.com/SNU-SSC-Lab/circuit-team-05/actions/runs/45407370057)은 `1c18d7d` 기준이며, GitHub의 안내는 계정 결제 실패 또는 사용 한도 상향 필요였다. 이 메시지만으로 두 원인 중 어느 쪽인지 확정할 수 없다. 해당 명령을 수동 재실행하지 않고 기록을 조회했다. 이 실행에서는 ASIC 로그나 리포트도 생성되지 않았다.

로컬 측정은 [당시 실행 기록](../../verification/asic/experiment-20261124.json), 전체 판정 조건은 [flow.py](../../scripts/asic/flow.py), GitHub 실행 순서는 [asic.yml](../../.github/workflows/asic.yml)에서 확인할 수 있다. 실행 기록에는 기준 커밋과 미커밋 수정 여부·소스 해시도 남아 있다. 그 기록 자체를 새 실행의 합격 근거로 사용하지 않는다.

## 10. 중간에 실제로 실패했고 해결한 부분

| 문제 | 원인으로 확인한 것 | 적용한 해결과 남은 한계 |
| --- | --- | --- |
| Magic 설정을 현재 키트에 적용 | INVX1에 공개 `.10`/`.30` 기술파일을 적용했을 때 DRC 오류 타일 49/55개와 핀 추출 문제가 발생 | 실제 코어 경로는 KLayout 추출 + Netgen으로 구성. Magic의 현재 NSPL 호환·PEX 정확도는 계속 미확인 |
| 셀 핀 접근·배선 | 38개 셀 LEF의 VIA1 장애물 도형이 원본 GDS의 CONT 도형과 일치 | 해시·도형 일치를 확인한 작업용 LEF에서 층 표기를 수정. 원본 도형을 삭제하지 않음 |
| 클록 핀 부근 short | 내부 MET2 전원선이 CLK 핀의 접근점을 막음 | 전원 링을 코어 밖으로 옮기고 MET1 전원선을 연결 |
| 첫 코어 LVS 불일치 | 개별 셀 검사에서 핀 대응·소자 속성 차이가 발생. 34종 중 2026-11-24 추출·비교 경로에서 23종 일치, 11종 미확인. 2026-11-28 원인 확인: 병렬 MOS `m=`, 직렬 입력 순서, split gate를 키트 deck처럼 줄이지 않음 | 새 ASIC 흐름에서만 11종을 제외. 셀 자체 불량으로 단정하거나 핀·W/L 검사를 끄지 않음. 이후 코어 LVS 통과. 11-28 `lvs_reduce.py`로 34종 모두 일치, 합성 제외 목록은 아직 그대로 |
| 배선 도구 DRC 0인데 독립 검사 실패 | KLayout이 새 배선의 VIA1/CONT 간격·겹침 마커 262개를 검출 | 공정의 cut 층 간격·적층 금지 조건을 작업용 기술 LEF에 추가. 재배선 후 해당 검사 오류 0건 |

이 과정 때문에 **배선 도구 DRC 0건**, **코어 LVS 일치**, **전체 공정 DRC/LVS 통과**를 따로 기록한다. Netgen의 종료 코드 0도 회로 일치를 뜻하지 않아 6절처럼 완료 표시·로그·JSON을 함께 판정한다.

세부 경위는 [SPEC 0017의 비교 실험과 실행 결과](../specs/0017-rtl-to-gds.md), 셀별 근거는 [cell-qualification.json](../../verification/asic/cell-qualification.json)에 있다. 위 문제를 해결했다고 아직 옮기지 않은 공정 규칙까지 검증된 것은 아니다.

## 11. 남은 R&D: 무엇이 있고 무엇을 더 해야 하나

### 전체 DRC

공개 키트에 Calibre·Assura 규칙 원본이 있다. 원본이 없어서 멈춘 작업이 아니다. 활성 209개 중 113개를 옮겼고(넓은 금속의 조건부 간격·via 둘러싸기는 SPEC 0021), 나머지 96개와 전역 입력 플래그는 아직 지원하지 않는다. 별도 antenna deck은 SPEC 0020에서 옮겼다. well의 전위·연결 조건, tap·guard ring·ESD 등은 단순 폭/간격 수치만 복사해서 구현할 수 없다.

다음 실험은 [대조표](nspl-drc-rule-matrix.md)에서 미구현 규칙 하나를 골라 원본 식의 정상·위반·경계 예제를 만들고, KLayout 결과를 원본 도구 결과와 비교하는 것이다. 옮긴 96개 규칙은 2026-11-28 Calibre golden과 판정이 같다(fixture 451개 중 449개 일치·2개 제외, 실제 형상 변형본 1차 609개·2차 798개에서 불일치 0, `verification/reliability/table.md`). 113개 미구현 규칙의 fixture Calibre 판정도 받아 두었다(`verification/reliability/golden/drc-unported-20261128/`). Assura와의 대조는 하지 않았다. `96/209`를 공정 검증률로 해석하지 않는다.

원본끼리도 FVTN/FVTP, PAD 치수, antenna 활성 상태에 차이가 있다. 차이를 임의로 합치지 말고 [대조 기록](nspl-drc-rule-audit.md)의 해당 식을 기준으로 적용 규칙을 확인해야 한다.

### 공정 RC·PEX

키트에 ITF·ICT·TLUplus·QRC·MIPT와 셀 PEX 예제가 있다. 부족한 것은 **우리 배선과 도구에 적용해 정확도를 확인한 추출 설정 및 기준 결과 대조**다. 현재 `core_flow.tcl`은 보정되지 않은 `set_wire_rc`와 전역 배선 추정으로 `estimated.spef`를 만든다. 아직 상세 배선 GDS의 정밀 PEX를 끝내고 그 값을 STA에 연결한 경로가 아니다.

먼저 작은 배선 패턴 하나에서 공정·corner·층·폭·간격·길이를 고정한다. 기존 QRC 자료의 형식·단위·패턴 대응을 확인하거나, 호환되는 기준 추출 환경에서 같은 패턴의 R·접지 C·결합 C를 얻는다. 후보 Magic/OpenRCX 경로의 결과와 비교한 뒤 다른 길이·간격에서도 차이를 확인하는 순서로 연구할 수 있다. 허용 오차는 기준 도구·비교 조건과 함께 팀이 정해야 하며 아직 확정된 수치는 없다.

현재 GPIO와 코어 사이의 조립 배선은 코어 P&R 뒤 KLayout에서 추가된다. 코어 OpenRCX만 연결해도 이 배선까지 추출되는 것은 아니다. 코어와 조립 배선의 RC 포함 범위를 함께 확인해야 한다. Magic이 원래 PEX 기능이 없는 도구라는 뜻도 아니다. 현재 NSPL 설정으로 R·C가 맞게 나오는지를 확인하지 못한 것이다.

### GPIO·ESD를 포함한 전체 칩 LVS와 타이밍

공개 키트에 GPIO GDS와 OA(OpenAccess) 원회로가 있다. 조사한 아카이브에서는 사용할 GPIO의 텍스트 SPICE/CDL과 타이밍 Liberty를 찾지 못했다. 따라서 원회로가 없다고 단정할 수는 없고, 호환 환경에서 내보내거나 별도 제공받는 경로가 필요하다.

PIC·POB4·PVDD·PVSS 중 작은 셀 하나부터 독립 기준 SPICE/CDL과 GDS 추출을 비교해야 한다. 현재 코어용 추출기에서 다루지 않은 저항·ESD 등 소자와 핀·모델 대응도 확인해야 한다. 지금 통과한 pad→코어 금속 연결 검사는 이 트랜지스터·소자 수준 LVS를 대신하지 않는다. GPIO 지연·부하·공정 조건을 확인하지 못해 전체 칩 타이밍도 미확인이다.

### 핀맵·제출 기준

현재 SOP28 조립은 연결된 pad 28개를 둔 제안이다. 수업 안내서의 사용 핀 25개 이하 조건과 본딩·미사용 pad 처리, 필수 전원 수를 최종 확인하지 못했다. 이는 도구 설치로 해결되는 항목이 아니며 팀·수업 담당자와 정할 연결 조건이다. 서비스가 요구하는 검사 도구·규칙의 최종 적용 기준도 별도로 확인해야 한다.

공개 자료로 할 작업과 문의할 내용을 나눈 [자료·지원 요청문](pdk-support-request.md)이 있다. 이 요청문은 초안이며 발송하지 않았다.

## 12. 지금 사용법에서 R&D를 시작하는 순서

1. **3절의 451개 도형 시험, 4절의 코어 실행, 5절의 확장 DRC를 먼저 재현한다.** 기존 결과를 기준으로 보관한다. `--experimental`은 지정된 미확인 항목만 허용하며 실제 실패를 성공으로 바꾸지 않는다.
2. **연구 질문 하나를 고른다.** 예를 들어 미구현 DRC 한 규칙, GPIO 한 셀, MET1 배선 한 패턴으로 범위를 좁힌다. PEX 연구라면 8절의 설정·명령·입출력 예제를 함께 받으면 출발점을 비교하기 좋다.
3. **입력과 비교 조건을 고정하고 차이를 기록한다.** PDK·설정·입력 해시, 도구 버전, 명령, corner·단위, 기대 결과의 출처, 실제 출력과 오차·미지원 조건을 한 실험 묶음으로 남긴다. 현재 추출기의 결과를 다시 정답으로 넣지 않는다.
4. **해당 범위가 확인된 뒤 전체 흐름에 연결한다.** 작은 예제 통과를 전체 공정 지원으로 확대하지 않는다. DRC 목록·시험, 셀별 LVS, RC 대조 근거를 함께 늘린다.
5. **GitHub 실행 환경은 별도로 복구·재실행한다.** 실행기가 할당돼 설치부터 리포트 보관까지 실제 실행됐는지 확인한다. 그 뒤에도 공정 미확인 항목이 남으면 strict는 실패가 맞다. 원격 실행 복구와 제작 제출 준비 완료는 서로 다른 완료 조건이다.

관련 문서: [전체 흐름·지원 범위](rtl-to-gds-guide.md), [DRC 대조·시험 기록](nspl-drc-rule-audit.md), [자료·지원 요청문](pdk-support-request.md).
