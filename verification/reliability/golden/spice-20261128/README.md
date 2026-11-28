# ngspice ↔ Spectre 시뮬레이션 대조 (2026-11-28)

오픈소스 시뮬레이터 ngspice(키트 HSPICE 모델)와 상용 Spectre(키트 Spectre 모델)로 같은 회로 65개를 돌려 결과를 점마다 비교했다. 대응표(`../../table.json`)의 `spice` 칸 근거다. `summary.json`의 수치는 비교 CSV(sha256 `8127a69afa7c47901ee126d145b38d8c817162caa94d0e4d1ab8f7dc3ffeb5b2`)에서 계산했고, CSV·raw 파일·로그는 저장소 밖 근거 묶음(2026-11-28)에 있다.

## 조건

| 항목 | 값 |
| --- | --- |
| 실행일 | 2026-11-28 |
| 상용 | Spectre 20.1 isr17(sub-version 20.1.0, 빌드 534), 키트 `Model_Parameter/05cmos_mosfet_corner.scs`(tt/ss/ff/sf/fs)·`05cmos_model_241213.scs`(저항) 무수정 |
| 오픈소스 | ngspice-46, 키트 HSPICE `.lib`(level 49를 BSIM3v3.2로 읽음) |
| 모델 숫자 | 두 모델 파일의 corner 값(10개 × 6)과 nmos4·pmos4 파라미터(111개씩)를 비교해 차이 0 |
| 동작 조건 | VDD 5.0 V, 25 °C(키트 Liberty와 같음), 지연 50%, 전이 20–80% |
| 회로 | 회로 줄(DUT·전원·ramp·부하)은 두 deck에서 글자 그대로 같다. 측정은 같은 `measure.py` 코드 |
| 시험 65개 | NMOS·PMOS DC와 INVX1 VTC(5 corner), INVX1 과도(schematic, 키트 PEX netlist), GPIO 출력 패드 POB4·POB8·POB24·PBCT4·PBCT8 과도·DC(tt/ss/ff), 입력 패드 PIC·PBCT4·PBCT8 과도·VTC(tt/ss/ff) |

## 결과

| 비교 | 점 수 | 최대 \|상대오차\| | 어디서 |
| --- | --- | --- | --- |
| 과도(지연·전이) | 1244 | 1.5% | `invx1_tran_tt` 하강 지연(Liberty 표의 점 `slew2.2/load0.0034`) |
| DC 곡선 | 50873 | 3.67% | `invx1_vtc_fs` 출력, 입력 2.21 V 근처(그 시험의 중앙값 0.01%) |
| 측정값(Vt·Idsat·VIL 등) | 134 | 0.62% | `invx1_vtc_fs` VIL |
| GPIO 과도 | (과도에 포함) | 0.92% | `pob24_out_tran_tt` 하강 전이 |

DC 곡선의 최대 오차는 fs corner 인버터 VTC의 전환점(약 2.16 V) 근처, 입력이 조금만 달라도 출력이 크게 바뀌는 구간에서 나왔다.

## 바꾼 것과 한계

- ngspice는 키트 HSPICE `p2res`의 온도 항이 쓰는 HSPICE 변수 `TEMP`를 읽지 못한다. 같은 값(rsh 125, rcont 50, tc1 3.915e-4, tc2 3.647e-6, TNOM 27)을 ngspice 저항 온도계수로 다시 써서 `p2res_ngspice.sp`로 넣었다. Spectre는 키트 `.scs`를 그대로 썼다.
- auCdl netlist를 SPICE로 옮기며 `/ INV2` 표기의 `/`를 지우고, `$[p2res]` 소자를 키트 `p2res` subckt 호출로 바꿨다.
- ngspice는 HSPICE 모델 파라미터 `N`·`FC`를 무시한다고 알렸다. 접합이 순방향일 때만 영향이 있어 이번 시험(역바이어스)에는 영향이 작다고 본다. Spectre는 이 둘에 경고가 없었다.
- Spectre는 `-raw .`로 실행하면 raw 파일을 열지 못해 실패했고, `-raw raw`로 다시 실행했다. deck은 고치지 않았다.
- GPIO는 원회로(K1 schematic)만 있어 셀 내부 기생이 빠진 낙관적인 값이다. 표준셀은 키트 Liberty가 PEX netlist로 특성화된 것으로 보인다(INVX1 schematic은 Liberty보다 지연이 중앙값 45% 빠르고, 키트 PEX netlist는 3.5% 차).
- 두 시뮬레이터가 같다는 것은 같은 모델 숫자를 같은 식으로 계산한다는 뜻이다. 실리콘 측정과 맞는다는 뜻은 아니다. 키트에는 온도·전압 corner가 없다.

서버 이름·주소·계정·경로와 원본 로그는 공개 저장소에 넣지 않는다(SPEC 0019).
