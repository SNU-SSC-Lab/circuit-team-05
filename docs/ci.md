# RTL CI 실행과 결과 해석

PR 3은 전체 검사를 매 PR에서 실행한다. main 병합 후 push와 수동 실행도 지원한다. GitHub Actions 실행 상태는 PR의 Checks에서 확인한다. 팀은 핫픽스 대응 여지를 두기 위해 GitHub branch protection과 필수 상태 검사를 별도로 설정하지 않는다. CI 결과를 보고 병합 여부를 판단하며, 기존 로컬 main 차단 훅과 평상시 PR 흐름은 유지한다.

GitHub에는 `pr-policy`, `policy-unit (ubuntu-24.04)`, `policy-unit (windows-2022)`, `rtl`의 네 job이 표시된다. 아래 다섯 RTL 검사 이름은 `rtl` job의 단계 이름이다. 도구를 한 번만 설치하고 결과를 한곳에 보관하기 위해 묶었다. 앞 RTL 검사가 실패해도 뒤 검사는 실행하며 최종 실패는 유지한다.

## 검사 이름

| 이름 | 검사 내용 |
| --- | --- |
| `pr-policy` | PR의 What·Why·How, SPEC 연결과 RFC 버전. 로컬 이벤트 파일을 생략하면 문서만 검사 |
| `policy-unit` | 문서 검사·훅·push 차단·이벤트 입력·시험 결과 판정기의 시험 |
| `rtl-lint` | Verilator 정적 검사, 이어서 Icarus 컴파일. 앞 단계 실패 시 실패로 종료 |
| `rtl-unit` | 9개 하위 모듈과 독립 정답 모델 |
| `rtl-integration` | 경계값·위치·오류·입력 공백·연속 작업·입출력 중 리셋 |
| `rtl-regression` | 6,561개 합법 가중치 배열 × 5개 입력 배열, 고정 seed 무작위 10,000작업 |
| `rtl-coverage` | 통합·회귀 시험을 Verilator에서 다시 실행해 RTL 줄 커버리지 집계 |

전체 시나리오와 RFC 대응은 [scenarios.json](../verification/scenarios.json), 기획과 합격 조건은 [SPEC 0012](specs/0012-rtl-ci.md)에 있다. 테스트 이름은 역할을 나타내며 국제 표준으로 정해진 이름은 아니다.

## 로컬 실행

RTL 시험은 Linux에서 실행한다. Windows에서는 WSL Ubuntu를 사용했다. Python 환경에 [requirements-ci.txt](../requirements-ci.txt)를 설치하고 Icarus·Verilator·C++ 빌드 도구를 준비한다. cocotb 2.0.1의 공식 지원 하한은 Icarus 11.0, Verilator 5.036이다. 배포판 기본 패키지가 이 조건을 만족한다고 가정하지 않는다.

Workflow는 Python 3.12.3·cocotb 2.0.1, Ubuntu 24.04의 Icarus 패키지와 공식 소스에서 빌드한 Verilator 5.048을 사용한다. Verilator 커밋은 `d0aa828c217410fffc73d92077b6f4f54830357c`로 고정했다. 최초 실행에는 도구 빌드 시간이 추가되며 이후 캐시를 재사용한다. 정책 시험 제한 시간은 10분, RTL은 25분이다. 로그·JUnit·커버리지·실행 코드와 규약 버전은 Actions artifact에 7일 보관한다. 비공개 PDK·학교 라이선스는 사용하지 않는다.

```sh
python -m pip install -r requirements-ci.txt
python scripts/ci_policy.py
python -m unittest discover -s tests/policy -v
python scripts/run_rtl.py unit
python scripts/run_rtl.py integration
python scripts/run_rtl.py regression
python scripts/run_rtl.py coverage
python scripts/run_rtl.py lint
```

Windows의 정책 시험도 같은 `unittest` 명령을 사용한다. 실제 PR 본문을 검사하려면 `ci_policy.py --event 이벤트파일.json`으로 GitHub 이벤트 형식의 본문과 base·head SHA를 전달한다. 본문은 셸 명령으로 실행하지 않는다.

전체 시간을 순서대로 측정하려면 다음 명령을 사용한다. 앞 검사가 실패해도 다음 검사를 측정하며 최종 종료 코드는 실패를 유지한다.

```sh
python scripts/benchmark_ci.py --build-root /var/tmp/ssc-ci-build
```

`--repeats 3`으로 반복 횟수를 늘리거나 `--suites rtl-regression rtl-coverage`로 대상을 고를 수 있다. 결과는 `.policy-tmp/benchmark/benchmark.json`과 검사별 로그·JUnit·통계에 저장한다. 빌드 결과는 재사용하므로 첫 빌드와 재실행 시간을 구분한다. 측정 중에는 무거운 검사를 동시에 실행하지 않는다.

## 측정 범위와 한계

2026-11-12 로컬 환경은 Intel Core i7-1355U, WSL2 Ubuntu, Python 3.12.3, cocotb 2.0.1, Icarus 14.0 개발 버전 `f49307688`, Verilator 5.051 개발 버전 `7e80ea657`이다. 저장소는 Windows 디스크, 빌드 디렉터리는 WSL의 `/var/tmp`에 두었다. 이 버전 조합의 로컬 실행을 확인했으며 GitHub runner에서의 재현은 별도로 확인해야 한다.

측정에는 Python 검사 실행·시뮬레이터 빌드와 시뮬레이션이 포함된다. 최초 도구 설치·다운로드·WSL 시작·GitHub 대기·결과 업로드는 포함되지 않는다. GitHub 실행 시간과 같다고 보장하지 않는다.

### 로컬 측정 결과

아래는 빌드 결과를 재사용한 최종 1회 측정값이다. 통계적 평균으로 해석하지 않는다. 앞서 실행한 전체 회귀도 72.3초에 통과했다.

| 이름 | 실행 시간 | 결과 |
| --- | ---: | --- |
| `pr-policy` | Linux 1.7초 / Windows 0.3초 | 문서 검사 통과. 게시 전이므로 실제 PR 이벤트 판정은 미실행 |
| `policy-unit` | Linux 23.5초 / Windows 73.7초 | 두 환경 통과. 각 50개 시험 중 Linux는 Windows 전용 1개 생략 |
| `rtl-lint` | 0.5초 | 경고 11개로 실패 |
| `rtl-unit` | 8.5초 | 하위 모듈 9개와 모델 시험 3개 통과 |
| `rtl-integration` | 3.5초 | 4개 시나리오, 정상 결과 확인 102작업 통과 |
| `rtl-regression` | 72.2초 | 32,805개 경계 작업 + 무작위 10,000작업 통과 |
| `rtl-coverage` | 53.3초 | 통합·회귀 6개 시나리오 통과, 줄 계측 96/98 |

Linux 기준 순차 합계는 약 2분 43초다. Windows 정책 시험 시간은 별도다. Linux 정책 시험의 최초 실패는 venv를 활성화하지 않아 Bash가 Windows Python 실행 경로를 찾은 환경 문제였다. 실행기가 자신과 같은 Python 경로를 자식 프로세스에 전달하도록 고친 뒤 두 운영체제에서 재실행했다. 최초 실패 로그도 남겼다.

재현 자료는 `.policy-tmp/benchmark/benchmark.json`, `.policy-tmp/policy-benchmark-linux/benchmark.json`, `.policy-tmp/policy-benchmark-windows/benchmark.json`에 있다. 첫 파일의 정책 시험 실패는 뒤의 수정 후 재실행 결과와 구분한다. 모든 RTL 시험 수와 결과는 첫 파일의 검사별 `summary.json`에도 기록했다.

## 커버리지와 합격 기준

### 첫 GitHub 실행 확인

[2026-11-12 실행](https://github.com/SNU-SSC-Lab/circuit-team-05/actions/runs/43169698622)은 head `b6da055`의 문서 검사·Ubuntu/Windows 정책 시험·RTL 다섯 단계와 결과 업로드를 모두 통과했다. Python 3.12.3, Icarus 12.0 stable, Verilator 5.048로 실행했다. RTL 단계 자체는 lint 0.08초·단위 1.55초·통합 0.52초·회귀 50.86초·커버리지 35.50초였다. 최초 도구 설치·소스 빌드 시간은 별도이며 최신 커밋의 통과 여부는 PR Checks에서 확인한다.

### 수치의 의미

첫 집계는 Verilator가 만든 RTL 줄 계측 지점 98개 중 96개에 도달했다. **97.96%는 이 계측 지점의 도달률**이며 전체 입력 공간의 검사 비율이나 오류가 없을 확률이 아니다. 단순 연결·조합식 등 도구가 줄 계측 지점을 만들지 않은 코드는 분모에 포함되지 않는다. 분기·토글·전체 기능 교차 커버리지는 이번 수치로 측정하지 않았다.

미도달 지점은 `dot8_controller.v` 110~111행의 `default` 복구 분기다. 상태는 2비트이며 정상 상태 네 값이 모두 정의돼 있다. 이 시험은 정상 상태와 리셋을 검사하며 강제 상태 손상이나 X/Z 상태 주입을 검사하지 않았다. 제외 항목은 **없다**. 이 분기를 제외할지는 설계자와 검증자가 근거를 검토해야 한다.

별도로 컨트롤러 단위 시험은 정상 상태 4개와 정상 전이 8개를 모두 관찰했다. 필수 시나리오는 전부 통과해야 한다. 코드 커버리지는 미도달 항목과 함께 보고하며, 임의의 80%·90%를 안전 보장선으로 쓰거나 수치를 높이기 위해 시험을 삭제하지 않는다.

## lint 수정과 제외 근거

최초 측정에서 기존 RTL 경고 11개로 실패했다. 열 파일에 마지막 개행만 추가했고, `weights[15:2]` 미사용 한 건은 [lint.vlt](../verification/lint.vlt)에 파일·경고 종류·메시지를 한정해 제외했다. 그 뒤 로컬 lint와 Icarus 컴파일은 통과했다. 연산·통신 로직과 기대 결과는 바꾸지 않았다.

top은 현재 항의 `weights[1:0]`만 읽는다. 상위 비트는 `weight_shift_reg` 내부에서 저장·이동되고 다음 항에서 하위 비트가 된다. 이 연결에 대한 경고만 제외하며 다른 미사용 신호나 파일 끝 개행 경고는 그대로 검사한다. 설계자는 이 근거와 연결을 PR에서 검토해야 한다. 이 lint 제외는 RTL 줄 커버리지 제외가 아니다.

참고: [cocotb 2.0.1 시뮬레이터 지원](https://docs.cocotb.org/en/v2.0.1/simulator_support.html), [OpenTitan 검증 방법론](https://opentitan.org/book/doc/contributing/dv/methodology/index.html).
