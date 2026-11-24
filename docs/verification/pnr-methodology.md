# P&R 이후 검증 방법론

팀 공유용 검토 초안 v0.3 · 2026-11-24

목적은 **RTL에서 맞던 계산이 실제 셀과 배선으로 바뀐 뒤에도 동작하고, 공정 규칙에 맞는 최종 GDS를 제출하는 것**입니다. 현재 CI는 실제 NSPL 합성·게이트 회귀·배치 전 타이밍까지 실행하며, 실제 배치배선·GDS 생성은 아직 없습니다. 앞으로 CI가 구현과 검증을 함께 수행하도록 확장합니다.

구현 순서와 도구 비교는 [SPEC 0017](../specs/0017-rtl-to-gds.md), 팀원이 결과를 읽는 방법은 [전체 흐름 안내](rtl-to-gds-guide.md)에 있습니다. **1팀 Qflow 방식과 OpenROAD를 같은 예제로 비교한 뒤 선택합니다.** 이 문서는 검사할 내용과 공식 제출 검토를 설명하며 특정 도구의 채택이나 제출 승인을 뜻하지 않습니다.

공유된 「SNU MyChip VCore·PCore 5Team Design Guide」(김태완, 2026-10-18) 3·6~8쪽을 기준으로 정리했습니다. 3쪽은 SOP28·공식 pad 배치를, 8쪽은 최종 DRC/LVS/PEX의 검증된 deck와 다른 도구의 공정 지원 확인을 설명합니다. 원문은 저장소에 재배포하지 않습니다. 오픈소스 검사 통과와 제작 서비스의 인정 여부는 별도 항목입니다.

## 확인된 내용과 실행 환경의 미확인 사항

초기 모듈 명세 DOCX에는 학교 서버·계정·접속 방법이 없습니다. 설계 안내서 4쪽은 Cadence 접근과 PDK 사용 권한 등이 준비돼 있다는 전제를 두고, 4차 공고가 제공하는 자동 배치·배선 환경을 출발점으로 사용하라고 설명합니다. 이 내용만으로 학교 리눅스 서버가 제공된다고 확인할 수는 없습니다.

이 문서의 이전 버전은 학교 서버를 실행 환경으로 가정했습니다. 그 존재와 제공 여부를 확인한 사실이 아니므로 해당 표현을 정정합니다. 먼저 실제 지원 환경의 제공 주체·접속 방법·도구와 사용 권한을 확인해야 합니다.

| 구분 | 현재 상태 |
| --- | --- |
| 안내서가 설명한 내용 | Cadence·PDK 접근 전제, 공고의 자동 배치·배선 환경 확인, 합성 이후 검증 흐름 |
| 현재 확인한 내용 | 공개 4차 NSPL 키트의 고정 해시, 기존 Yosys·게이트 회귀·OpenSTA 실행. 공개 Magic·Netgen 설정은 현재 키트 지원 확인이 더 필요 |
| 아직 확인하지 않은 내용 | 학교 서버 제공 여부, NSPL 전체 칩의 오픈소스 P&R·DRC/LVS·배선 RC 경로와 자원 요구량 |
| 첫 실행 환경 후보 | 로컬 Linux/WSL에서 비교·재현한 뒤 GitHub Linux 실행기. 별도 VM은 실제 자원 측정 후 판단 |
| GitHub 연동 | 선택한 도구·공정 설정·결과 판정을 고정하고 전체 흐름을 연결할 계획 |

## RTL 검증에서 무엇이 더 필요한가요?

| 질문 | 확인 방법 |
| --- | --- |
| 합성하면서 계산이나 상태가 달라졌는가? | RTL과 합성 netlist의 등가 검증, gate-level 기능 회귀 |
| 배선 지연까지 포함해 제시간에 값이 도착하는가? | RC 추출 후 setup·hold 정적 타이밍 분석(STA) |
| 실제 셀 모델과 지연을 넣어도 외부 입출력이 맞는가? | 타이밍 모델·SDF를 적용한 gate-level 시뮬레이션 |
| 그린 도형이 공정의 폭·간격 등 규칙을 지키는가? | 공식 deck의 DRC |
| 그린 배선과 소자가 의도한 회로와 연결이 같은가? | LVS |
| 제출 파일을 다시 열었을 때도 같은 칩인가? | 최종 GDS 재반입과 DRC/LVS 재실행 |

P&R은 셀을 배치하고 배선을 연결하는 작업입니다. STA·DRC·LVS·기능 회귀는 그 결과를 서로 다른 관점에서 검사합니다. 한 검사 통과가 다른 검사를 대신하지 않습니다.

## 검증 흐름

```mermaid
flowchart TD
    A[RTL 기능 검증 통과·기준 커밋 고정] --> B[합성: 실제 표준셀과 SDC 적용]
    B --> C[동일 기능 확인: 등가 검증 또는 한계를 명시한 회귀]
    C --> D[Floorplan·전원망·pad 연결]
    D --> E[셀 배치·클록 트리·배선]
    E --> F[배선 기생성분 추출]
    F --> G[STA: setup·hold와 제약 누락 확인]
    F --> H[Gate-level: 셀 모델·SDF 기능 회귀]
    E --> I[최종 GDS 생성·별도 library로 재반입]
    I --> J[pad 포함 전체 chip의 공식 DRC·LVS]
    G --> K[같은 최종 설계 버전의 증거 모아 리뷰]
    H --> K
    J --> K
    K --> L[공식 제출 조건 확인 후 MPW 제출]
```

타이밍이나 물리 오류를 고치면 해당 설계에서 결과를 다시 만듭니다. 앞 버전의 타이밍 보고서와 뒤 버전의 GDS를 섞어 제출하지 않습니다. 마지막 수정 후 영향을 받는 등가·타이밍·기능·물리 검사를 다시 확인합니다.

## 시작 전에 받아야 할 자료와 도구

| 준비물 | 필요한 이유 | 현재 확인할 사항 |
| --- | --- | --- |
| 정확한 ETRI 공정명·PDK 버전·공식 튜토리얼 | 허용 소자·층·검증 경로 결정 | 실제 배포 버전과 제출 서비스 조건 |
| 표준셀·pad의 Liberty와 기능·타이밍 모델 | 합성, STA, gate-level 시뮬레이션 | 지원 전압·온도·공정 조건과 누락 모델 |
| tech/cell LEF·셀 GDS·layer map | 셀 배치·배선·GDS 출력 | 표준셀·pad·전원핀 이름 일치 |
| RC 추출 기술 자료 | 배선 저항·용량 반영 | 지원 추출 도구와 제공 corner |
| 공식 DRC/LVS/PEX deck와 소자 모델 | 공정 규칙·연결·기생성분 검증 | 운영기관이 인정하는 도구·버전·실행법 |
| 전체 chip의 LVS 기준 회로와 셀·pad 참조 netlist | 레이아웃과 의도한 연결 비교 | 코어뿐 아니라 pad·전원 연결까지 같은 top으로 비교 |
| SDC와 보드 I/O 조건 | 클록·입출력 타이밍 정의 | 실제 FPGA 송수신 시점, pad 지연·부하 |
| 도구가 지원하는 실행 환경·설치 파일·라이선스 | 합성·P&R·검증 도구 실행 | 제공 주체·접속 방법·지원 OS/CPU·실제 사용 권한 |

아래는 안내서 기준의 상용 도구와 역할입니다. 이번 오픈소스 경로의 채택 목록은 아닙니다. 오픈소스 후보와 필요한 공정 설정은 SPEC 0017에서 비교합니다.

| 단계 | 안내서 기준 또는 지원 후보 | 확인할 결과 |
| --- | --- | --- |
| 합성 | Genus | mapped netlist, SDC, 셀·면적·경고·타이밍 보고서 |
| 등가 검증 | Conformal, 제공될 경우 | RTL ↔ 합성 netlist의 비교 결과 |
| 배치배선·클록 트리 | Innovus | 배선 완료 DB, 연결·설계 규칙 검사, netlist·GDS |
| RC 추출 | 공정이 지원하는 Quantus·Calibre 등 | SPEF 등 지원 형식과 추출 조건 |
| 최종 STA | Tempus 또는 공정이 지원하는 sign-off STA | 제공 corner별 setup·hold와 제약 누락 |
| Gate-level 시뮬레이션 | Xcelium과 공식 셀 모델·SDF | 기능 회귀, 타이밍 위반, SDF 적용 내역 |
| DRC·LVS·PEX | 공식 deck를 지원하는 Assura·Calibre 등 | 최상위 chip의 공정 규칙·연결·추출 결과 |

Vivado는 FPGA 구현을 담당합니다. ETRI PDK만 추가해 CMOS ASIC의 합성·P&R·물리 검증 도구로 사용할 수는 없습니다. 공개 RTL 도구만으로 위 상용 도구와 공식 검증 경로가 준비됐다고 볼 수도 없습니다.

## 단계마다 무엇을 확인하나요?

### 1. 합성 전: 검사할 설계를 고정합니다

RTL 검증을 통과한 Git 커밋, 대상 top, RTL 목록, 관련 RFC·SPEC을 기록합니다. 현재 `v_ternary8_top`은 코어이며, pad를 포함한 전체 chip top은 별도로 확인해야 합니다. 공유 안내서의 `MPW_PAD_28pin`에 어떻게 연결할지와 실제 사용 가능 영역을 확정합니다.

클록과 입력·출력 신호, 동기 리셋, 입력 전이 시간과 출력 부하를 SDC에 반영합니다. 초기 10 MHz는 주기 100 ns에 해당하지만 입력·출력 지연과 부하까지 정해 주지는 않습니다. 안내서의 초기 예시를 그대로 최종 제약으로 쓰지 않고 FPGA·pad·보드 조건으로 검토합니다. 동기 리셋을 일괄 false path로 처리해 타이밍 검사를 숨기지 않습니다.

### 2. 합성 후: 기능과 회로 구조를 확인합니다

실제 Liberty로 합성하고 unresolved reference·예상하지 않은 black box·폭과 부호 문제를 해결합니다. latch·순차소자·셀 수·면적을 확인합니다. 삼진 내적의 가산기 공유가 의도대로 합성됐는지도 보고서와 회로 구조에서 확인합니다.

오픈소스 등가 검증은 Yosys 기반 경로를 후보로 두고 순차 회로·리셋·셀 모델 지원을 먼저 확인합니다. 실행하지 못한 경우 gate-level 회귀·구조 검토와 **formal 등가 검증 미실시**를 구분해 기록합니다. 시뮬레이션 통과를 모든 입력에 대한 등가 증명이라고 부르지 않습니다.

### 3. 배치배선 중: 연결과 전원·클록을 확인합니다

전원·접지·pad·ESD rail, well/substrate 연결, filler·tap·endcap 등 필요한 구조를 공정 가이드에 맞춥니다. 클록 트리 합성(CTS) 뒤에는 클록 도착 시간 차이와 삽입 지연을 확인합니다. 허용 metal stack 안에서 배선하고 전원·클록·신호의 open/short, 혼잡과 설계 규칙 위반을 해소합니다.

선택한 P&R 도구의 내부 검사는 설계 중 오류를 찾는 데 사용합니다. 이 결과만으로 전체 공정 DRC/LVS를 통과했다고 표시하지 않습니다. 최종 GDS 재반입·공정 규칙·독립 기준 회로 비교가 필요합니다.

### 4. 배선 후: 실제 지연과 기능을 확인합니다

지원 RC 자료로 기생성분을 추출하고, 제공된 slow/fast 등 조건에서 setup과 hold를 모두 검사합니다. 아래 조건은 안내서에 따른 종료 증거이며 실제 sign-off corner·mode 목록을 함께 남겨야 합니다.

| 항목 | 확인할 종료 증거 |
| --- | --- |
| 타이밍 | 검사한 조건별 WNS ≥ 0, TNS = 0. setup·hold 위반 없음 |
| 제약 | 모든 의도된 clock·endpoint 검사. 누락 제약과 미검토 경로 없음. 예외는 이유와 리뷰 기록 |
| 기능 | 마지막 항·오류·리셋·연속 작업을 포함한 gate-level 회귀 통과 |
| 지연 모델 | 실제 netlist와 셀 모델·SDF 버전 일치. annotation 결과와 누락·경고의 검토 기록 |
| 물리 규칙 | 공식 DRC 0건 또는 운영기관이 인정한 waiver만 남음 |
| 연결 | LVS 일치. 임의의 black box·미검토 불일치로 통과 처리하지 않음 |
| 제출 파일 | 최종 GDS를 별도 library로 재반입하고 전체 chip DRC/LVS 재실행 |

SDF는 셀과 배선의 지연을 시뮬레이터에 적용하는 자료입니다. cell 모델이나 RC·GPIO 타이밍 자료가 없으면 임의의 값을 만들어 빈칸을 채우지 않습니다. 제공 기관과 담당 멘토에게 가능한 대체 검증과 남는 한계를 확인하고, 해당 범위를 미실행 또는 제한 검증으로 표시합니다.

RTL에서 사용한 정답 모델과 입력 시나리오는 재사용할 수 있습니다. 다만 실제 chip top의 pad·포트 연결, 리셋, 셀 모델과 지연 적용에 맞게 시험기를 확인해야 합니다. SDF 기능 회귀는 실행한 입력의 동작을 확인하며 모든 타이밍 경로를 검사하는 STA를 대신하지 않습니다.

## GitHub에서 P&R 검증도 실행할 수 있나요?

**오픈소스 도구를 고정한 Linux 환경에서 직접 구현·검증하도록 연결할 계획입니다.** 학교 서버나 상용 라이선스를 전제로 하지 않습니다. 먼저 로컬에서 후보를 비교하고 NSPL 지원과 자원을 측정합니다.

기존 Yosys·게이트 시험·OpenSTA 코드를 재사용하고, 선택한 P&R 도구·KLayout GDS 병합·공정 검사·RC 추출을 연결합니다. GitHub workflow는 실행·캐시·결과 보관을, 스크립트는 단계 실행과 판정을 담당합니다. 이번 문서 PR에서는 도구 설치·workflow 구현·runner 등록을 수행하지 않습니다.

```mermaid
flowchart LR
    A[후보 비교 · NSPL 지원 확인] --> B[고정 Linux 환경]
    B --> C[PR의 RTL에서 합성 · P&R · GDS 생성]
    C --> D[DRC · LVS · 배선 RC · STA · 기능 회귀]
    D --> E[입력 해시 · 요약 · 원본 보고서 · GDS 보관]
    E --> F[통합 검사 결과와 함께 사람이 리뷰]
    F --> G[팀장 수동 병합]
```

이는 목표 흐름입니다. 현재 초록색 Checks가 전체 칩 구현 완료를 뜻하지는 않습니다. 새 필수 결과가 없거나 실행하지 못하면 전체 통과로 표시하지 않습니다. 브랜치 보호는 추가하지 않고 팀장이 검사 범위·결과와 리뷰를 확인해 병합합니다. 공식 제출 검토는 별도로 남깁니다.

### 본인 소유 OCI·AWS VM을 쓰는 경우

본인이 클라우드 VM을 만들고 실행 환경을 구성하는 방식도 가능합니다. 다음 조건을 확인하고 선택합니다.

- 설치할 EDA 도구가 VM의 OS와 CPU 구조를 지원해야 합니다. 예를 들어 x86-64 바이너리는 Arm VM에서 그대로 실행할 수 없습니다.
- 해당 라이선스가 개인 클라우드 환경에서의 실행을 허용해야 합니다. Cadence는 고객이 마련한 공용 클라우드에서 도구를 사용하는 Cloud Passport 모델도 안내하지만, 우리 프로젝트에 제공될 사용 권한은 아직 확인하지 않았습니다.
- PDK·표준셀·공식 검증 deck를 해당 클라우드에 보관·사용해도 되는지 제공 조건을 확인해야 합니다.
- GitHub self-hosted runner 등록에는 저장소 또는 조직의 관리자 권한이 필요합니다. VM 생성 권한과 구분합니다.

무료 VM 할당량·CPU 종류·지원 도구·실제 메모리 요구량을 확인한 뒤 사양과 비용을 정합니다. VM만 확보한 상태를 합성·P&R 환경 준비 완료로 표시하지 않습니다.

## 실행마다 남길 기록

한 번의 실행 결과에는 다음 자료를 함께 묶습니다. 제한된 원본 파일은 제공 기관이 허용한 위치에 두고 GitHub에는 허용된 요약과 위치 식별 정보만 남깁니다.

- Git 커밋, RTL 목록·top, 관련 RFC·SPEC과 SDC 버전
- PDK·셀·도구·deck·RC 자료의 버전, 실행일, corner·mode
- 실제 명령·스크립트, 입력 DB·netlist·GDS의 식별값과 보고서 위치
- 등가·setup·hold·DRC·LVS·SDF·기능 회귀의 통과·실패·미실행 상태
- 경고·waiver·미검증 항목의 이유, 검토자와 후속 조치

WNS는 검사한 경로 중 가장 작은 여유 시간이며 음수면 위반입니다. TNS는 음수 여유 시간의 합입니다. 이 수치만 제시하지 않고 어떤 corner와 경로를 검사했는지 같이 남깁니다. 최종 제출 GDS의 식별값으로 모든 종료 증거가 같은 설계를 가리키는지 확인합니다.

## 다음에 확정할 일

1. 현재 NSPL 키트의 셀·층·핀·DRC/LVS·RC 지원을 작은 셀로 확인합니다.
2. 같은 예제로 1팀 Qflow 방식과 OpenROAD를 비교하고 결과로 선택합니다.
3. 5팀 코어를 구현·검사하고 시간·메모리를 측정합니다.
4. 전체 칩 pad·전원·I/O 조건을 검토한 뒤 chip 범위와 CI를 구현합니다. 필요한 규약 변경은 별도 RFC로 검토합니다.

공식 도구 설명: [Innovus](https://www.cadence.com/en_US/home/tools/digital-design-and-signoff/soc-implementation-and-floorplanning/innovus-plus-synthesis-implementation-system.html), [Tempus](https://www.cadence.com/en_US/home/tools/digital-design-and-signoff/silicon-signoff/tempus-timing-signoff-solution.html), [Quantus](https://www.cadence.com/en_US/home/tools/digital-design-and-signoff/silicon-signoff/quantus-extraction-solution.html), [Calibre](https://www.siemens.com/en-us/products/ic/calibre-design/physical-verification/), [GitHub self-hosted runner](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/add-runners). 제작 가능 여부는 해당 공정의 공식 자료와 제출 심사에서 확인합니다.

클라우드 환경 참고: [Cadence Cloud Passport](https://www.cadence.com/en_US/home/solutions/cadence-cloud/cloud-passport.html), [OCI Always Free](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm), [AWS Free Tier](https://aws.amazon.com/free/free-tier-faqs/). 무료 제공 범위는 계정 유형과 확인 시점에 따라 달라질 수 있어 실행 환경이 정해질 때 다시 확인합니다.
