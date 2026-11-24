# 5팀 DRC·LVS 사용 방법과 현재 검증 범위

성준님 공유용 · 2026-11-24 · PR #11 작업 브랜치 기준

**전체 칩의 제출용 검증은 아직 미완료다.** 실제 NSPL 검사는 KLayout으로 도형 검사·소자 추출을 하고 Netgen으로 회로를 비교한다. 처음 공유한 Magic 경로는 별도의 `scmos` 연습 시험에 남아 있다.

| 구분 | 확인한 범위 | 남은 일 |
| --- | --- | --- |
| DRC | 원본 활성 209개 대조, 구현한 기하 검사 96개에서 코어·패드 포함 GDS 오류 0건. 도형 시험 427개 통과 | 113개 규칙·전역 입력 플래그 이식, Calibre/Assura 결과 대조 |
| LVS | 내적 코어의 실제 GDS 추출 회로와 독립 기준 CDL 일치 | GPIO·ESD를 포함한 전체 칩 LVS |
| 기능 | 최종 netlist의 6개 시험·42,907작업 회귀 통과 | 실제 제작 칩·보드 시험 |
| RC·PEX | 추정 배선 RC와 탐색용 SPEF 생성 | 공정에 맞춘 RC 모델·정밀 추출·정확도 대조 |

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

첫 명령은 원본 활성 209개 검사와 목록이 같은지 확인한다. 두 번째는 GDS로 저장·재반입한 정상/위반·수치 경계·계층 도형 427개를 시험한다. `selftest.json`의 `status: pass`는 **정상 도형을 통과시키고 의도한 오류를 잡았다는 뜻**이다. `golden_compared`는 false이며 원본 도구와의 동등성 검증은 아직이다.

재실행할 때는 `-02`처럼 새 출력 폴더를 지정한다. 실행기는 이전 결과를 덮어쓰지 않는다.

## 4. 우리 코어 생성·LVS·기능 시험 재현

```bash
export TEAM05_OUT="$HOME/ssc-team05-runs/core-01"
python scripts/run_asic.py --pdk "$TEAM05_PDK" --openroad "$TEAM05_TOOLS/openroad" --target core --experimental --out "$TEAM05_OUT"
python -m json.tool "$TEAM05_OUT/result.json"
```

합성 → 배치·클록 트리·전원망·배선 → 실제 셀 GDS 병합 → GDS 소자 추출 → Netgen LVS → 최종 netlist 기능 회귀 순서다. 로컬 전체 실행은 약 3~4분대였지만 PC·도구 버전에 따라 달라진다.

실험 재현을 위해 `--experimental`을 명시했다. 지정된 미확인 공정 항목 외의 필수 검사를 실행·통과해야 종료 코드 0을 허용한다. JSON의 전체 `status: incomplete`와 `ready_for_submission: false`는 유지한다. 옵션을 빼면 현재는 끝까지 산출물을 만들어도 미확인 항목 때문에 1로 종료한다. 실제 LVS 불일치나 미실행을 성공으로 바꾸는 옵션은 아니다.

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

4절이 끝난 뒤 같은 입력을 새 폴더에 복사해 비교 단계를 재현할 수 있다. 기준 회로의 include 파일도 함께 복사한다.

```bash
export TEAM05_LVS_RECHECK="$TEAM05_OUT/lvs-recheck-01"
mkdir "$TEAM05_LVS_RECHECK"
cp "$TEAM05_OUT/lvs/"{layout.spice,schematic.spice,cells.spice,run.tcl} "$TEAM05_LVS_RECHECK/"
(
  cd "$TEAM05_LVS_RECHECK"
  export SSC_TOP=v_ternary8_top
  export SSC_EXTRACTED="$TEAM05_LVS_RECHECK/layout.spice"
  export SSC_SCHEMATIC="$TEAM05_LVS_RECHECK/schematic.spice"
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

현재 GitHub 실행은 계정 결제/사용 한도 문제로 실행기 할당이 차단된 상태다. 위 사용법은 로컬 재현 경로이며 이번 GitHub 실행에서 산출물을 받았다고 안내하지 않는다.

관련 문서: [전체 흐름·지원 범위](rtl-to-gds-guide.md), [DRC 대조·시험 기록](nspl-drc-rule-audit.md), [자료·지원 요청문](pdk-support-request.md).
