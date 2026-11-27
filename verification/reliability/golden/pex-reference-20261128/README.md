# PEX 기준 자료: Calibre xRC (2026-11-28)

배선 저항·용량 추출(PEX)을 오픈소스 OpenRCX로 보정하고 대조할 때 쓸 상용 기준 자료가 무엇이고 어디에 있는지 적는다. 대응표(`../../table.json`)의 `pex` 칸 근거 기록이다. 판정은 여전히 근거 없음(미검증)이다. 기준 자료는 받았지만 OpenRCX 쪽 보정·대조를 아직 하지 않았기 때문이다.

큰 출력 파일(DSPF·SPEF·svdb)과 GDS는 저장소에 넣지 않는다. 모두 저장소 밖 근거 묶음(2026-11-28, C5 항목)에 있고, 아래 sha256으로 찾는다.

## 무엇을 받았나

| 실행 | 입력 | 출력 | corner |
| --- | --- | --- | --- |
| 패턴 | 시험 패턴 GDS 164종(이름 있는 net 374개): 단일선 26, 판 위 단일선 18, 평행 두 선 78, 판 위 평행 두 선 12, 세 선 12, 교차 12, via 사슬 6. MET1/2/3·POLY1, DRC 최소 폭·간격과 팀 `technology.lef`의 기본 폭·pitch | DSPF(`TEST_LVS.spf`, LAYOUTNAMES) | typical, bestRC, worstRC |
| 코어(gate 수준) | 오픈소스 흐름 코어 `v_ternary8_top` GDS, source는 `final.v` 이름을 유지한 netlist | SPEF(`v_ternary8_top.spef`, SOURCENAMES = `final.v` 이름, D_NET 468개). 실행마다 LVS CORRECT | typical, bestRC, worstRC |
| 코어(트랜지스터 수준) | 같은 코어 | DSPF(`TEST_LVS.spf`, 4.3 MB) | typical |

모든 실행에서 xRC 오류 0. corner는 실행 폴더의 `LPE_LIB/typical_rules.{C,R}`를 키트 `<corner>_rules.{C,R}`로 연결해 골랐다(deck 글은 그대로). 각 실행의 `pdb.log`에서 `ETRI_0.5UM_CMOS_Typical`·`BestRC`·`WorstRC`가 읽힌 것을 확인했다. 코어 SPEF는 이름을 맞춘 뒤 STA 대조(`../sta-20261128/`)에 썼다.

| 파일 | sha256 |
| --- | --- |
| 패턴 GDS `c5_patterns.gds` | `c506bdf60cf4bdf3b98e3423fd1b7789dd8a4c62a316bab65f64f7e579ccfdc8` |
| 패턴 DEF `c5_patterns.def`(같은 금속 도형, OpenRCX 입력용) | `41f5eb72bfff9643dd5775912c2cfb5ac6e0530f6ab32aa04e1389db04046533` |
| 패턴 목록 `c5_patterns.json` | `be8b5b8ea59dfc1d453543bdf7869f90f14ae8617c98f2760fd2f77ec1713839` |
| 코어 GDS `v_ternary8_top.gds` | `fa6ab910b7f03fd4c966c9c19b2455fd7f26297614c1f20ccb221fed9b09ea93` |
| 코어 DEF `final.def` | `77e823d01476c16ded7c20964c0367f3227a6fe8038146c1653570c6cf40991d` |
| 패턴 DSPF typical / bestRC / worstRC | `9a774d46610ef03d3a7878b4c8459ee63bcaafebaea12e5456ad31bc68c2f203` / `217889ad6254e7f6d18b69f664748fcb4480afc698f9604a42f7a76cadbf13d9` / `a52346966fcb17e92934b2914e6eb004f55da21e7cfd0064da52c8ca69861c4c` |
| 코어 SPEF typical / bestRC / worstRC (Calibre 출력 그대로) | `8e21afbca4cecc44c0d3a4d9282694848c62ba2ddf42b7cff5a632bdb8521681` / `2669111119771266e22a1045e020fc8f946728b19ed27b6bedf2c36501ae3031` / `66aa04ffe62f36d8d10e5637666ef7059330de154f474fa7932b892a781a842b` |
| 코어 트랜지스터 수준 DSPF typical | `996b7d8a4c2062c7bffe59c8f033ff26e148498856518a2a19def13bf9ac65d3` |

## 실행 조건

| 항목 | 값 |
| --- | --- |
| 실행일 | 2026-11-28 |
| 도구 | Calibre `v2023.4_17.10` (xRC) |
| PEX deck | 키트 `Calibre/PEX/NSPL_0p5um_Analog_CMOS_2P3M_5V_V1.1_PEX.cal`, sha256 `bd605b58e450ad173a32afebbde067a37a85562501b4b0e26680f7a87bbf57cc`. 아래 한 단어만 바꾼 실행 폴더 사본을 썼다 |
| header | 키트 `pex_header.cal`에서 최상위 셀 이름만 바꿈 |
| 명령(패턴·트랜지스터 수준) | `calibre -xrc -phdb` → `calibre -xrc -pdb -rcc` → `calibre -xrc -fmt -all` |
| 명령(코어 gate 수준) | `calibre -lvs -hier -hcell xcells.txt -ixf -nxf -spice svdb/v_ternary8_top.sp header.cal` → `calibre -xrc -pdb -rcc -xcell xcells.txt header.cal` → `calibre -xrc -fmt -all header.cal`. 이 판의 `-phdb`는 SOURCENAMES에 필요한 교차 참조(XDB)를 만들지 않아 LVS로 시작했다 |

### PEX deck 한 단어 수정 기록

키트 PEX deck은 그대로는 batch xRC가 돌지 않는다. `calibre -xrc -phdb`가 `ERROR: MASK SVDB DIRECTORY statement does not contain the XRC option.`으로 멈춘다. header에서 같은 문장을 덮어쓰는 방법은 Calibre가 거부했다(`superfluous specification statement: mask svdb directory`). 그래서 실행 폴더에 deck 사본을 만들고 62행에 `XRC` 한 단어만 더했다. 키트 deck 파일은 건드리지 않았다.

```
62c62
< MASK SVDB DIRECTORY "svdb" QUERY
---
> MASK SVDB DIRECTORY "svdb" QUERY XRC
```

실행 스크립트는 사본과 키트 deck의 차이를 미리 적어 둔 diff(`expected_svdb.diff`)와 비교하고, 한 글자라도 다르면 실행 전에 멈췄다. 코어 gate 수준 실행은 이 사본에 두 줄(LAYOUTNAMES → SOURCENAMES, 출력 형식 SPEF)을 더 바꿨고, 키트 deck 대비 전체 diff를 실행 폴더마다 남겼다(`full_spef.diff`·`full_dspf.diff`). deck 수정이 불가피할 때의 절차는 `../../CHECKPOINT.md` 7절에 있다.

## Quantus는 실행할 수 없었다

- Quantus 21.2.2-p045로 패턴 typical을 시도했다. 먼저 `EXTQRCXOPT-221 Unable to map technology corner "typical"`이 났다. 키트 `Assura/QRC`에 `typical/ best/ worst/` 폴더는 있지만 `corner.defs`가 없다. 실행 폴더에 링크와 `corner.defs`를 만들어 넘겼다(키트 무수정).
- 그다음 `EXTGRMP-354 There is no cell-level data in the unified techfile.`로 멈췄다. 키트 qrcTechFile은 Assura 트랜지스터 수준 추출용이라 셀 수준(LEF/DEF) 추출 자료가 없다.
- Innovus 23.14 `extractRC`로 같은 qrcTechFile을 쓰는 방법도 `IMPEXT-3491`(활성 RC corner에 Quantus 기술 파일이 없음)로 실패했다.
- 그래서 PEX 상용 기준은 Calibre xRC다. 미검증 목록 `pex`의 해소 조건도 Calibre xRC와의 대조로 적었다.

## 아직 하지 않은 것

- OpenRCX 보정: 같은 패턴 DEF로 OpenRCX를 돌려 Calibre DSPF와 넷별 R·C를 비교하고, 공정 RC 설정을 맞추는 일은 아직 하지 않았다.
- 지금 흐름의 `estimated.spef`는 배선 R·C가 모두 0이다(기술 LEF에 층별 RC가 없음). 흐름의 타이밍은 배선 RC 0인 분석이다. 미검증 목록 `wire-rc-zero`.
- 키트 PEX deck의 PEX MAP에는 MET1/2/3·via·접점만 있고 POLY1·확산 맵은 주석이다. POLY1 패턴은 이것을 확인하려고 넣었고, 결과 분석은 보정 작업에서 한다.

서버 이름·주소·계정·경로와 원본 로그는 공개 저장소에 넣지 않는다(SPEC 0019).
