"""Fixtures of DRC/ANT rules KLayout does not implement yet, with their Calibre verdicts (2026-11-28).

The three groups were written outside this repository in the `drc_cases.py` format and run through
Calibre one GDS at a time (golden: verification/reliability/golden/drc-unported-20261128/):

- C1a: front-end rules (well, active, poly, implant, contact) + FLAG SKEW / ACUTE / NONSIMPLE, 229 fixtures
- C1b: metal/via/pad spacing and enclosure + all 12 RULECHECKs of the separate ANT deck, 330 fixtures
- C1c: device-recognition rules (resistor, PIP cap, BJT, ESD, latch-up, diodes), 298 fixtures

`drc_cases_pending_c1a.py`, `_c1b.py` and `_c1c.py` are the generator files copied unchanged (line endings
LF), so `reliability.case_sha256` of every case equals the hash in the manifest of the GDS Calibre read.
`fail` was our hypothesis; three fixtures are corrected below to what Calibre reported, and each record keeps
the hash of the definition Calibre ran (`run_case_sha256`). The two fixtures Calibre refused as input
(C1a 0225/0226, self-crossing polygons) stay as run: `raises` means our GDS writer or KLayout raises, as in
drc_cases.py, and the golden marks those two `refused` with Calibre's reason (excluded, like 0169/0170).

These fixtures are not in `drc_cases.py`: `drc_fixture_test.py` requires every fixture rule to be a KLayout
port. When a rule is ported, move its fixtures to `drc_cases.py` and its golden entries with them.
"""
import json

import reliability
# No `as` aliases and no module objects in variables: baseline_guard.py's scan allows only
# <pending module>.cases / .records / .cases_with_meta (SPEC 0019).
import drc_cases_pending_c1a
import drc_cases_pending_c1b
import drc_cases_pending_c1c

# (group, GDS name Calibre ran) -> fields replaced by the Calibre verdict, and why.
CORRECTIONS = {
    ('C1a', '0227-NONSIMPLE-self-touching-vertex.gds'): (
        {'fail': False}, 'Calibre는 꼭짓점 하나로만 닿는 두 사각형을 NONSIMPLE로 보지 않음(경고 0)'),
    ('C1b', '0315-ANT_06_01-boundary.gds'): (
        {'fail': True}, '정확한 산술로는 한계와 같지만 Calibre는 위반으로 판정(124). 계수 83.33의 부동소수점 계산으로 허용값이 아주 조금 작아짐'),
    ('C1b', '0323-ANT_06_02-boundary.gds'): (
        {'fail': True}, '정확한 산술로는 한계와 같지만 Calibre는 위반으로 판정(124). 계수 83.33의 부동소수점 계산으로 허용값이 아주 조금 작아짐'),
}


def _decks(group):
    if group == 'C1b':
        return [record['deck'] for record in drc_cases_pending_c1b.records()]
    return None


def records():
    """One dict per fixture: group, index (in its group), gds, deck, case, run_case_sha256, correction."""
    result, used = [], set()
    for group, group_cases_of in (('C1a', drc_cases_pending_c1a.cases), ('C1b', drc_cases_pending_c1b.cases),
                                  ('C1c', drc_cases_pending_c1c.cases)):
        # JSON round trip: plain lists and dicts, so the hash and the GDS see the same shapes.
        group_cases, decks = json.loads(json.dumps(group_cases_of())), _decks(group)
        for index, case in enumerate(group_cases):
            gds = reliability.fixture_name(index, case)+'.gds'
            change, why = CORRECTIONS.get((group, gds), ({}, None))
            if change:
                used.add((group, gds))
            result.append({'group': group, 'index': index, 'gds': gds, 'deck': decks[index] if decks else 'DRC',
                           'case': dict(case, **change), 'run_case_sha256': reliability.case_sha256(case),
                           'correction': why})
    if used != set(CORRECTIONS):
        raise ValueError('corrections name fixtures that do not exist: '+', '.join(sorted(map(str, set(CORRECTIONS)-used))))
    return result


def cases():
    return [record['case'] for record in records()]
