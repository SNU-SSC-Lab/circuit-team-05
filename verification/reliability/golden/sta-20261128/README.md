# OpenSTA ↔ Tempus 타이밍 대조 (2026-11-28)

오픈소스 흐름 코어 `v_ternary8_top`의 타이밍을 같은 입력으로 OpenSTA(오픈소스)와 Tempus(상용)에서 계산해 끝점마다 slack을 비교한 결과다. 대응표(`../../table.json`)의 `pnr-sta` 칸 근거다. `summary.json`의 Tempus 값은 Tempus 보고서에서, OpenSTA 값은 같은 날 로컬 실행 결과에서 옮겼다. 보고서 원본은 저장소 밖 근거 묶음(2026-11-28)에 있다.

## 같은 입력

| 입력 | 내용 | sha256 |
| --- | --- | --- |
| netlist | 흐름의 `final.v` | `1ffd0df62cfd19918932dd9c11f1b55ed84f7b30b68f171b9550b87e0cad3d35` |
| 제약 | 흐름의 `constraints.sdc`(Tempus는 아래 사본) + 두 도구 모두 `set_propagated_clock [all_clocks]` | `6fd6c5c442951e1cb66885ebc6485f9e0947ea7cbf48c7ef17702fecae878cc3` |
| Liberty | 키트 `NSPL_0p5um_Digital_CMOS_2P3M_5V_V1p1_12T_std_tt.lib`(TT, 5.0 V, 25 °C) | `0c84f0d970d374ba5c9c4cf7aec22fec96e306f8be373bda9ef20ce2bb48de51` |
| 배선 RC | Calibre xRC 코어 SPEF 3 corner(`../pex-reference-20261128/`) | typical `d2907b81e98d1179fa46171e9b1c8dd55d9a25be625908e0166c05b666f83747`, bestRC `70fa24c6abcd68d226381f29465f831bbb5e4074e4865e02bfa30670822d6630`, worstRC `c25375c62b9423e1250a40d9a4a037b4081deadac8bbb7c5202e0f850917d5f0` |

SPEF는 Calibre가 낸 그대로는 이름이 netlist와 맞지 않아 로컬에서 두 가지만 고쳤다. (1) 인스턴스 이름 앞의 `X`를 뗐다(`final.v`에 있는 인스턴스만, 남은 것 0). (2) Calibre는 넷 이름을 모두 대문자로 쓰고 Tempus는 대소문자를 구별하므로, 넷 이름을 `final.v` 표기로 되돌렸다(못 찾은 D_NET 0). 저항·용량 값은 건드리지 않았다. 위 sha256은 고친 파일이고, 두 도구가 같은 파일을 읽었다. Tempus에서 실제 넷 470개 중 VDD·VSS를 뺀 468개에 RC가 붙었다(annotation).

## SDC 문법 차이

`constraints.sdc` 2행의 `delete_from_list`는 OpenSTA 전용 명령이다. Tempus는 이 줄을 건너뛰고(`WARNING (CTE-25)`), 그 결과 3행 `set_input_delay`와 5행 `set_driving_cell`이 빈 핀 목록 오류(`ERROR (TCLNL-312)`)로 빠진다. 입력이 지연 0으로 들어가 Tempus hold가 −4.958 ns(SPEF 없음)로 나왔다. Tempus용 사본(sha256 `2a041646012af645320c72cb10771496e520cf9e63efff97c31623fe0b7c6bd9`)은 2행만 바꿨다.

```
2c2
< set data_in [delete_from_list [all_inputs] [get_ports CLK]]
---
> set data_in [remove_from_collection [all_inputs] [get_ports CLK]]
```

사본으로는 오류 없이 읽힌다. 흐름의 SDC가 상용 도구에서 그대로 안 읽힌다는 사실은 미검증 목록 `sdc-portability`에 남긴다.

## 결과 (Tempus는 SDC 사본, OpenSTA는 원본 SDC)

끝점 72개(setup·hold 각각)가 두 도구에서 같고, 차는 끝점마다 |OpenSTA − Tempus| slack이다. OpenSTA 지연 계산기는 기본 `dmp_ceff_elmore`와 `arnoldi` 둘 다 돌렸다.

| corner | Tempus 최악 setup / hold (ns) | OpenSTA dmp_ceff_elmore setup / hold (ns) | setup 최대 차 (ns) | hold 최대 차 (ns) | hold 평균 차 (ns) |
| --- | --- | --- | --- | --- | --- |
| typical | 48.444 / 1.895 | 48.3162 / 1.6104 | 0.244 (arnoldi 0.249) | 0.346 (arnoldi 0.348) | 0.048 |
| bestRC | 48.572 / 1.902 | 48.4225 / 1.6158 | 0.247 (arnoldi 0.253) | 0.353 (arnoldi 0.350) | 0.049 |
| worstRC | 48.308 / 1.888 | 48.1502 / 1.6042 | 0.244 (arnoldi 0.249) | 0.348 (arnoldi 0.352) | 0.048 |

- 세 corner 모두 setup 차 최대 0.253 ns, hold 차 최대 0.353 ns다. 최악 hold 끝점은 두 도구 모두 `_819_/D`(Tempus 1.895, OpenSTA 1.610, typical)다.
- 수치 차이는 기록만 한다. 허용 오차는 팀이 정할 때까지 게이트 조건으로 쓰지 않는다(SPEC 0019).

## 지금 흐름의 배선 RC는 0이다

흐름이 만드는 `estimated.spef`는 D_NET 468개 모두 총 C 0, 저항 4373개 모두 0이고 CAP 항목이 없다. 팀 `technology.lef`에 층별 RC가 없어서 OpenROAD `estimate_parasitics`가 0을 쓴다. 그래서 `estimated.spef`를 넣은 OpenSTA와 SPEF 없는 OpenSTA가 같은 값(setup 49.1454 / hold 1.6356 ns)을 낸다. 위 대조는 Calibre SPEF를 넣은 것이고, PR마다 도는 흐름의 타이밍은 배선 RC 0인 분석이다. 미검증 목록 `wire-rc-zero`에 남긴다.

## 이 결과로 말할 수 있는 것과 없는 것

- 같은 netlist·Liberty·SPEF·제약이면 OpenSTA와 Tempus의 끝점 slack은 위 차 안에서 같다(코어 1건, 3 corner).
- Innovus P&R과의 비교, GPIO·패키지 지연을 넣은 칩 단위 타이밍은 없다(미검증 `pnr-sta-vs-innovus-tempus`).

도구 판: Tempus Timing Solution `v23.14-s089_1`, OpenSTA `3.1.0`. 서버 이름·주소·계정·경로와 원본 로그는 공개 저장소에 넣지 않는다(SPEC 0019).
