# SPEC 0014 MyChip PDK 검사

- 상태: 이 저장소(3-A 삼진 내적)에 먼저 켠다. 다른 팀은 각자 판단해 같은 파일 하나로 켤 수 있다.
- 이후 변경: 검사 코드는 [SPEC 0015](0015-own-pdk-checks.md)에서 이 저장소로 옮겼다. 아래 How의 통합 저장소 재사용 workflow·deploy key 설명은 그 전의 기록이다. 검사 내용(What)은 그대로다.
- 기준: `main` 위의 단일 PR. 기존 `RTL CI`(SPEC 0012)와 `MyChip integration`(SPEC 0013)은 바꾸지 않는다.
- 관련 규약: RFC 0001 HW01~HW06(현재 회로 계약), RFC 0002 PR01·AUTO01.

## What

`.github/workflows/pdk.yml`을 추가한다. PR과 `main` 커밋마다 동아리 통합 저장소 [SNU-SSC-Lab/circuit-integration](https://github.com/SNU-SSC-Lab/circuit-integration)의 재사용 workflow `pdk.yml`을 이 저장소의 해당 커밋으로 실행한다. 결과는 PR에 `MyChip PDK` 체크로 붙는다.

검사 내용:

- 합성: 4차 PDK(NSPL_05CMOS_PDK_260820) 표준셀로 RTL을 합성한다(Yosys). latch·tri-state 셀, 표준셀로 바꿀 수 없는 구문, 조합 루프, 구동 없는 net이 있으면 실패한다. 셀 수·플립플롭 수·면적을 보고한다.
- 게이트 수준: 합성 netlist에 통합 검사와 같은 핀 수준 시험기와 안내서 golden 모델을 돌린다. 셀 동작은 PDK Liberty의 function을 따른다.
- 타이밍: OpenSTA로 10 MHz에서 setup·hold를 본다. PDK에 typical 라이브러리만 있어 setup은 지연 ×1.5, hold는 ×0.7로 계산한다.
- `mychip/`: 팀이 올린 합성·배선 netlist에 같은 시험기·타이밍을, 사인오프 리포트에 DRC 0건·LVS 일치·top 이름·GDS 해시 형식을 확인한다. 없는 단계는 실패가 아니다.
- 자체 검사: `` `ifdef SYNTHESIS ``로 RTL 시뮬레이션에서 숨긴 버그를 이 검사가 잡는지, 2 ns 클록에서 타이밍이 실패하는지 매번 확인한다.

또 `mychip/README.md`의 안내 문장을 이 체크 기준으로 고친다. RTL·테스트·기존 workflow는 바꾸지 않는다.

## Why

통합 검사(SPEC 0013)는 다섯 칩이 서로 맞물리는지(핀·handshake·응답 시간·reset·결과 형식)만 본다. 실제 칩으로 가는 길(합성 결과가 RTL과 같은지, 10 MHz를 맞추는지, 사인오프 결과)은 팀마다 진행 속도와 도구가 달라 각 팀이 필요할 때 켜는 검사로 분리했다. 이 저장소는 RTL이 완성돼 있어 먼저 켠다.

## How

workflow 하나가 통합 저장소의 재사용 workflow(`pdk.yml`)를 호출한다. 이 저장소는 workflow의 기본 토큰으로 읽고, 통합 저장소는 이미 설정된 읽기 전용 deploy key(Actions secret `CIRCUIT_INTEGRATION_KEY`)로 읽는다. 쓰기 권한은 요청하지 않는다(`contents: read`). PDK는 공개 사본(ETRI050 키트 저장소)을 고정 커밋에서 받아 SHA-256을 확인하고 캐시한다. 이 저장소에는 PDK 파일을 두지 않는다.

현재 `main`(f3aa77f)을 같은 검사로 돌린 결과: 합성 386셀·플립플롭 66개·면적 0.227 mm², 게이트 수준 시험 전부 통과, setup 여유 40.6 ns·hold 여유 1.53 ns(지연 ×1.5/×0.7), 자체 검사 2건 모두 검출.

흐름 변경: 없음
시각화 생략 이유: RTL 블록·순서·연결과 기존 CI 흐름을 바꾸지 않고, PR에 체크 하나가 추가된다.

## RFC 확인

RFC 0001의 회로 계약(입력 10바이트, 출력 4 nibble, 12비트 부호·오류 플래그, 응답 상한, reset)은 이 검사가 쓰는 시험기·golden 모델과 같다. 이 PR은 RFC 0001을 바꾸지 않는다. RFC 0002 PR01에 따라 별도 브랜치·PR로 제안하고, AUTO01에 따라 자동 검사 결과와 사람의 판단을 구분한다. 합성·타이밍 통과를 공식 Cadence 사인오프나 제작 가능 판정으로 표시하지 않는다.
