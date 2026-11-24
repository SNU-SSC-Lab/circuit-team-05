# 공개 NSPL DRC 규칙 대조·시험 결과

2026-11-24 · SPEC 0018 · PR #10 위의 후속 작업

**Calibre 원본의 활성 검사 209개와 비활성 7개를 목록화했다. 이 중 96개를 KLayout 기하 검사로 옮겨 정상·위반 등 427개 도형 시험을 통과했다. 나머지 113개와 원본 도구 교차 대조는 미완료다.** 이 수치는 구현 항목 수이며 공정 검증률이나 제작 준비율이 아니다.

전체 번호·원본 줄·본문 해시·이전 검사·추가 구현·부족한 조건은 [전체 대조표](nspl-drc-rule-matrix.md)와 [기계 판독 목록](../../verification/asic/drc-rules.json)에 있다. 담당자에게 전달할 글은 [별도 요청문](pdk-support-request.md)에 정리했다. 발송하지 않았다.

## 무엇을 대조했나

| 자료 | 확인한 역할 |
| --- | --- |
| 260820 키트의 Calibre DRC v1.1 | 이번 이식의 기준. 전체 활성 블록과 주석 처리된 블록을 구분해 추출 |
| 같은 키트의 Assura DRC v1.1 | ID·offGrid 이름 대조 및 식의 차이 조사. 같은 ID가 같은 동작을 뜻한다고 가정하지 않음 |
| 공개 ETRI 저장소의 KLayout 변환본 | 구현 참고. 일부 규칙 비활성·분리된 ID·다른 유도 도형을 확인 |
| PR #10의 routing 검사 | 기존 검사와의 대응. 복합 enclosure 이름과 넓은 금속 근사 등 부분 구현을 표시 |

원본 위치·SHA-256은 목록 JSON의 `sources`에 있다. Calibre 원본은 `6c012073...19c4f0f`, Assura 원본은 `09ce215f...581109`다. 검사는 전체 해시를 비교하며 위 줄임 표기를 입력으로 사용하지 않는다. 원본 PDK는 수정하거나 Git에 복사하지 않는다.

숫자 규칙 외에 OFFGRID 42개와 SKEW도 209개에 포함된다. 전역 `FLAG NONSIMPLE/OFFGRID/ACUTE/SKEW`는 별도 미이식 항목이다. Calibre의 별도 ANT deck 전체를 이식한 작업도 아니다.

## 실제로 늘린 검사와 시험

96개에는 grid, well·active·poly·implant·금속 폭, 일부 간격·enclosure, contact/via 치수, 겹침·배치 누락 조건이 포함된다. 복잡한 원본 식을 bbox로 대신 계산하지 않는다. 전위가 같은 well/다른 well, `WITH WIDTH`의 넓은 금속 구분, finger 합계·guard ring·BJT·diode의 복잡한 조건은 미구현으로 남겼다.

427개 도형은 PDK 숫자를 별도로 지정한 시험 정의에서 만든다. 검사 코드의 값을 가져와 기대값을 만들지 않는다. 모든 구현 규칙에는 정상·위반이 있으며 다음 조건도 포함한다.

- 기준값 바로 아래·같음·바로 위, 겹침·맞닿음·일부 미피복
- 회전·반사·이동된 2단계 하위 셀의 위반과 보고 좌표
- hole이 있는 얇은 금속, 사각 bbox가 같지만 직사각형이 아닌 contact/via
- 허용된 contact bar의 양방향 회전, 잘못된 bar 길이
- POLY1 전체가 ACT와 상호작용하는 경우와 단순 교집합의 차이
- 원본 NODRC 마커 적용 범위. ESDI처럼 원본에서 마스킹하지 않는 층은 제외하지 않음
- 0.01µm grid를 표현할 수 없는 DB 단위 거부, 더 세밀한 DB 단위에서도 위반 확인

시험은 GDS로 저장한 뒤 다시 읽고 **목표 규칙의 오류 여부**를 확인한다. 다른 규칙의 오류만 나온 것을 해당 규칙 검출로 세지 않는다. 도형·좌표·기대값·결과는 `selftest.json`과 개별 GDS에 남긴다. 원본 Calibre/Assura의 실행 결과와 비교한 시험은 아니다.

## 원본에서 발견한 차이

| 항목 | 확인한 차이 | 현재 처리 |
| --- | --- | --- |
| `OFFGRID_FVTN` | Calibre 본문은 FVTP, Assura는 FVTN/FVTP 각각 검사 | Calibre 본문 그대로 구현하고 차이를 명시. FVTN까지 검사했다고 주장하지 않음 |
| `13.PAD.A` | Calibre 본문은 최소 폭 80µm, min/max 주석과 차이. Assura에는 별도의 사각 치수 식 | 최소 폭으로 시험. 80µm 초과를 임의로 금지하지 않고 적용 기준 질문 |
| 금속 antenna | Calibre DRC의 3개 metal ANT는 비활성, Assura에는 실행 식이 있음. 별도 Calibre ANT deck도 있음 | 어떤 검사 묶음을 제출에 적용할지 담당자 확인. 임의로 삭제·통합하지 않음 |
| 공개 변환본의 `NMOS`·`POLY1_ON_ACT` | 원본의 INTERACT 선택과 변환본의 AND 교집합은 다른 도형을 만들 수 있음 | 옮긴 식은 원본의 전체 polygon 선택을 유지하고 좁은 tail 반례로 시험 |
| Assura/변환본 ID 차이 | `7.CONT.E.1`·`7.SONT.S8`·`5.PSD.*` 등 다른 이름이 있음 | 같은 문자열이 없는 것을 곧바로 검사 누락으로 결론 내리지 않음 |

이름 대조는 전체 목록을 빠짐없이 살피기 위한 수단이다. 두 도구의 연결·edge·예외 의미가 같다는 판정은 아니다. 원본의 sealing-region 예외를 일반 셀·새 배선에 넓혀 적용하지 않는다.

## 실제 GDS에 적용

대상은 PR #10에서 만든 Yosys 0.33·Netgen 1.5.133 호환 실행의 코어와 제안 SOP28 GDS다. RTL이나 배선은 이번 작업에서 바꾸지 않았다. KLayout 0.28.16으로 새 검사 96개를 실행해 두 대상 모두 오류 마커 0개였다. GDS 해시·검사 코드 해시·원본 해시·도구 버전·실행 시간은 [실험 기록](../../verification/asic/drc-audit-20261124.json)에 남긴다.

| 대상 | 실행한 기하 검사 | 오류 마커 | 로컬 시간 |
| --- | --- | --- | --- |
| 코어 | 96개 | 0개 | 4.633초 |
| 제안 SOP28 | 96개 | 0개 | 13.595초 |

두 GDS 모두 원본 NODRC 면적과 실제 제외 면적은 0이었다. 오류 0건이어도 상태는 `incomplete`, `qualified_process_drc`는 false다. 아직 없는 113개 검사, 전역 입력 플래그, 원본 도구와의 대조를 통과한 결과가 아니다. 원본 NODRC 영역과 층별 제외 면적도 보고서에 기록한다.

## 재실행

저장소 맨 위에서 Ubuntu/WSL의 Python과 KLayout을 사용한다. 결과 폴더는 새 경로를 지정한다.

```sh
python scripts/asic/drc_catalog.py --pdk NSPL키트경로 --out 새목록폴더
python scripts/asic/drc_selftest.py --out 새시험폴더
python scripts/asic/drc_audit.py --pdk NSPL키트경로 --gds 코어.gds --top v_ternary8_top --out 새코어검사폴더
python scripts/asic/drc_audit.py --pdk NSPL키트경로 --gds 조립칩.gds --top ternary8_sop28 --out 새칩검사폴더
```

`drc_audit.py` 종료 코드 0은 목록 확인과 **구현된 기하 검사**에 오류가 없다는 뜻이다. JSON에는 미완료 상태가 남으며 제작 통과가 아니다. 위반·입력 변경·목록 누락·잘못된 공정 해시는 1로 끝난다. 예전 `drc.py` 기본 routing 프로필과 7개 연습 시험은 유지한다. 확장 기하 프로필은 이 감사 명령으로 별도 실행한다.

GitHub workflow는 원본 목록·확장 도형 시험을 먼저 확인하고 GDS 생성 후 코어/조립칩 감사를 따로 수행한다. 앞 ASIC strict 판정이 실패해도 GDS가 있으면 이 독립 검사는 실행한다. 요약과 결과는 같은 artifact에 7일 보관한다. GitHub 실행기 한도가 막혀 있으면 원격 미실행으로 기록한다. 현재 전체 ASIC strict 판정의 미확인 항목을 성공으로 바꾸지 않는다.

## 디자인 킷에서 더 알아낼 수 있는 것

| 자료 | 키트에 있는 내용 | 남은 작업 |
| --- | --- | --- |
| DRC | Calibre/Assura 원본과 관련 실행 header | 나머지 규칙 이식·교차 대조. 원본 간 차이의 최종 적용 기준은 담당자 확인 |
| RC | ITF·ICT·TLUplus·QRC·MIPT, QRC 패턴/모델 파일 | 형식·단위·geometry 대응 해석 후 OpenRCX 재사용 가능성 확인 |
| GPIO | GDS와 PIC/POB4/PVDD/PVSS 등의 OA 원회로 | OA를 읽는 호환 환경에서 원회로 SPICE/CDL 내보내기. 소자·핀·모델 대조 |
| 핀맵 | 표준 pad 위치·GPIO 도형 | 필수 전원·본딩/미사용 처리와 팀의 최종 보드 연결 확정 |

추가 조사에서 QRC typical의 `profiles`에 `.dat/.dat.gz` 90개, `models`에 `.net_ascii` 계열 자료가 있음을 확인했다. 일부 압축 표는 숫자열로 읽힌다. 다만 각 열의 물리량·단위·패턴 대응을 검증하지 않았으므로 기준 SPEF라고 부르지 않는다. 우선 형식 설명이나 기존 변환 경로를 요청하고, 재사용이 어렵다면 새 패턴의 기준 추출을 지원받는 순서로 요청문을 작성했다.

따라서 모든 추가 정보를 외부에서 새로 받아야 하는 것은 아니다. 키트의 정보를 변환·시험하는 작업은 우리가 진행할 수 있다. 서로 다른 deck의 적용 기준, 신뢰도 비교 결과와 최종 핀맵 승인은 코드나 파일명만으로 확정하지 않는다.
