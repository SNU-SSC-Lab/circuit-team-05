# Calibre LVS 결과 모음 (2026-11-28)

1·2차 실행에서 받은 Calibre LVS 결과 네 가지를 한곳에 요약했다. 대응표(`../../table.json`)의 `lvs-core`·`lvs-cells`·`lvs-chip` 칸 근거다. `summary.json`의 값은 Calibre 보고서(`lvs.rep`)에서 옮겨 적었고, 판정을 손으로 고치지 않는다. GDS·netlist·보고서 원본은 저장소 밖 근거 묶음(2026-11-28, 아래 sha256)에 있다.

## 공통 조건

| 항목 | 값 |
| --- | --- |
| 실행일 | 2026-11-28 |
| 도구 | Calibre `v2023.4_17.10` |
| PDK | 공개 tarball `NSPL_05CMOS_PDK_260820.tar.gz` sha256 `2e49115a08f6af96c1f8433130ad4316551b5eba9001a3133905b544166af954` |
| LVS deck | 키트 `Calibre/LVS/NSPL_0p5um_Analog_CMOS_2P3M_5V_V1.1_LVS.cal` 무수정, sha256 `4cebfddc77ab6b4fb20e869281a895be9933a900670c98ff792ed5204c6366e0` |
| header | 키트 `lvs_header.cal`(sha256 `59617401426050047494e0ef64976e463ea97a809832a0d5bde8de24fdbf05f2`)에서 최상위 셀 이름만 바꿈. GPIO 셀 단독 실행만 한 줄 추가(아래) |
| 명령 | `calibre -lvs -hier -spice layout.spi header.cal` |
| 수 | ports·nets·instances는 `[layout, source]`, 보고서의 INITIAL NUMBERS OF OBJECTS(병렬 MOS·finger를 합치기 전) 값 |

## 결과

| 실행 | 대상 | Calibre | 오픈소스 쪽 |
| --- | --- | --- | --- |
| 코어(1차 C3) | 오픈소스 흐름 코어 `v_ternary8_top`, source = 흐름의 `schematic.spice` + `cells.spice` | CORRECT. ports 15/15, nets 2096/2096, MN 1895/1895, MP 1895/1895 | 같은 GDS·같은 source로 KLayout 추출 + Netgen 일치 |
| 칩(2차 C7) | 오픈소스 흐름 SOP28 칩 `ternary8_sop28`(28 pad, 검토 전 제안 핀맵) | CORRECT, header 추가 줄 없음. ports 15/15, nets 2129/2129, MN 2745/1963, MP 2195/1934, R 7/7. 합친 뒤 nets 869/869, MN 21/21, MP 13/13, R 7/7. 경고는 `Unbalanced smashed mosfets were matched.` 하나 | 같은 GDS에서 KLayout 연결 검사(`asic-chip-connectivity`, 탐침 183개) 단선·합선 0, 코어 Netgen LVS 일치. 패드 내부 소자 LVS 없음 |
| 표준셀(2차 C6) | 키트 표준셀 34종, 키트 GDS ↔ 키트 CDL | 34/34 CORRECT | KLayout 0.28.16 + `scripts/asic/lvs_reduce.py` + Netgen 1.5.323: 2026-11-28 재검사 34/34 일치(`verification/asic/cell-qualification.json`). 2026-11-24에는 23종 일치, 11종 확인 못 함(`summary.json`의 `open_source`는 이 11-24 기록) |
| GPIO(1차 K1 + C4c) | 키트 GPIO 패드 9종, 키트 GDS ↔ Virtuoso auCdl 원회로 CDL | 9/9 CORRECT(PVDD만 `Unbalanced smashed mosfets were matched.`) | 없음 |

### 칩 source netlist

`ternary8_sop28.cdl`(sha256 `f9b09d1731fc8790c80bc14ab552a82e690316138fe3f446729925d8030bfce1`)은 저장소 밖에서 `build_cdl.py`로 만들었다. 코어 `schematic.spice`(`.include` 한 줄만 뺌), 키트 표준셀 CDL(`cells.spice`와 같은 파일), K1 패드 원회로(`PIC`·`POB4`·`PVDD`·`PVSS`, 무수정), 그리고 저장소의 `scripts/asic/chip.py`·핀맵(`verification/asic/pinmap.toml`, 상태 proposed)에서 만든 최상위를 합친 것이다. 최상위 port 15개는 pad 열림(PAD) 위 이름표 28개의 서로 다른 이름이다. pad ring이 각 pad의 VDD·VSS 레일을 이어 주므로 칩에서는 `VIRTUAL CONNECT` 없이 CORRECT가 나왔다.

### GPIO 셀 단독 실행의 header 한 줄

패드 셀 하나만 두면 VDD 레일 둘·VSS 레일 둘이 셀 안에서 따로 떨어진 net이라, deck의 `LVS ABORT ON SUPPLY ERROR YES` 때문에 추출이 멈춘다(1차 C4: 9개 중 8개). 칩에서는 pad ring이 이 레일을 잇는다. 그래서 GPIO 단독 실행만 header 끝에 아래 한 줄을 더했다. deck 파일은 고치지 않았다.

```
VIRTUAL CONNECT NAME "VDD" "VSS"
```

source CDL은 Virtuoso IC6.1.8 `auCdl`로 키트 OA 라이브러리 `ETRI_NSPL_GPIO_250610`에서 내보낸 것을 고치지 않고 썼다. 소자 이름 대응(`nmos4`·`pmos4`·`$[p2res]`·`ndiode`·`pdiode`)도 따로 필요 없었다.

### 표준셀 11종을 오픈소스 쪽이 처음 확인 못 한 이유와 고친 방법

`AND2X2 AOI21X1 BUFX4 INVX2 INVX4 INVX8 NOR2X1 OAI21X1 OAI22X1 OR2X2 TBUFX2`. Calibre는 34종 모두 CORRECT였다. 2026-11-28에 두 쪽 netlist와 Netgen 로그를 비교해 원인을 확인했다. 셀이 아니라 우리 대조 방법의 문제였다.

- property 오류 6종(AND2X2, BUFX4, INVX2, INVX4, INVX8, OR2X2): CDL은 `W=3u m=2`처럼 쓰고, KLayout 추출은 finger를 이미 합쳐 `W=6u` 한 개로 쓴다. Netgen `property default`는 W를 같은 값끼리만 합치는 기준(critical)으로 두어 `m`을 W에 곱하지 않는다(1.5.323 `netcmp.c`). 그래서 W 6u↔3u, M 1↔2로 속성이 달랐다(INVX2 로그). deck은 `LVS REDUCE PARALLEL MOS YES`로 합친다.
- 최상위 핀 맞춤 실패 4종(AOI21X1, NOR2X1, OAI21X1, OAI22X1): 직렬 2개의 순서가 반대다. 예: NOR2X1 layout `VDD-B-x-A-Y`, CDL `VDD-A-x-B-Y`. Netgen은 이름을 무시하면 같은 회로라서 A↔B를 바꿔 맞춘 뒤 핀 이름이 다르다고 실패했다. Calibre 보고서는 이 직렬을 `_smn2v`·`_sup2v`처럼 입력 순서가 없는 묶음으로 바꾼다(`LVS RECOGNIZE GATES ALL`). 같은 묶음이 DFF·LATCH·MUX·TBUF에도 있다.
- 불일치 1종(TBUFX2): CDL은 출력 직렬을 `Y-[EN m=2]-net43-[A m=2]-VSS`처럼 중간점 하나로 쓰고, layout은 중간점이 따로인 직렬 두 줄이다. 그래프가 달라 Netgen은 소자 수 10↔6으로 불일치였다. deck은 `LVS REDUCE SPLIT GATES YES`와 위 직렬 묶음으로 둘을 같게 본다.

고친 방법: `scripts/asic/lvs_reduce.py`가 두 netlist에 같은 줄이기(병렬 합치기, 직렬 순서 없애기, 같은 직렬 두 줄 합치기)를 하고, `verification/asic/netgen_setup.tcl`이 W/L 허용오차를 deck의 `TRACE PROPERTY ... 0`과 같은 0으로 둔다(Netgen 기본은 1%). W/L 비교·핀·소자는 그대로 비교한다. 같은 키트 셀에서 W·m·L·게이트 연결을 일부러 틀리게 고친 CDL 12개는 모두 불일치였고(W 0.44% 차이 포함), 고치지 않은 셀은 모두 일치였다. 같은 줄이기와 설정은 흐름의 코어 LVS(`asic-lvs`)에도 쓰인다.

## 이 결과로 말할 수 있는 것과 없는 것

- 오픈소스 흐름 코어와 SOP28 칩 GDS는 상용 Calibre LVS 기준으로 맞다(1건씩, 검토 전 제안 핀맵).
- 같은 칩에서 오픈소스 쪽 판정(연결 검사 + 코어 LVS)과 Calibre 칩 LVS는 같은 결론이다. 다만 오픈소스 쪽 패드 내부 소자 LVS는 아직 없다. 패드 내부는 Calibre(C4c 9/9, C7 칩)만 확인했다. 미검증 목록 `gpio-internal-lvs`에 남긴다.
- 우리 경로(KLayout 추출 + `lvs_reduce.py` + Netgen)는 키트 표준셀 34종 모두 일치로 확인하며, Calibre 34/34 CORRECT와 같은 판정이다(2026-11-28). 흐름 합성에서 이 11종을 빼 둔 목록(`verification/asic/cells.toml`)은 아직 그대로다.

## 입력 해시

| 파일 | sha256 |
| --- | --- |
| 코어 GDS `v_ternary8_top.gds` | `fa6ab910b7f03fd4c966c9c19b2455fd7f26297614c1f20ccb221fed9b09ea93` |
| 코어 source `schematic.spice` | `da41de1caf9ee1e08e06fb0fc9fafdc3c4dd64dfd014eb1efb3da7e92f57064c` |
| 표준셀 CDL(`cells.spice`, 키트 `..._12T_std.cdl`) | `281efca41e93e7f88cf59e18e64159f9772111cfee1f86647cbd6ac3703e9f11` |
| 칩 GDS `ternary8_sop28.gds` | `967bcad67c0f3a4df18e2faec2c10df65c33b27f6da0fef8794ce6168c550fdb` |
| 칩 source `ternary8_sop28.cdl` | `f9b09d1731fc8790c80bc14ab552a82e690316138fe3f446729925d8030bfce1` |
| 표준셀 GDS(키트 `..._12T_std.gds`) | `e42dc1fb4c9a31aaa669e8e4c3b93a4b0d6eea40a463f5eaef5dbd17b432618e` |
| GPIO GDS(키트 `ETRI_NSPL_GPIO_250610.gds`) | `7d54a4948e775fc3a99faf157f91a3510a82c22cc134d677de83dd2214b6e971` |

GPIO 셀별 auCdl netlist 해시는 `summary.json`의 `runs.gpio.source_sha256`에 있다. 서버 이름·주소·계정·경로와 원본 로그는 공개 저장소에 넣지 않는다(SPEC 0019).
