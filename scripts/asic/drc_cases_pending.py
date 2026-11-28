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
port. When a rule is ported, move its fixtures to `drc_cases.py` and its golden entries with them: the
entries are copied unchanged into a new fixture golden folder (golden files are never edited), the rule
goes into MOVED_RULES and is verified in drc-rules.json, and only then `check-pending` reads the pending
golden's entries of that rule as moved (`reliability.check_pending`).

Moved so far: the 12 ANT deck RULECHECKs (102 fixtures, drc_antenna.py; golden/ant-fixtures-20261128),
including the two ANT_06 equality fixtures Calibre fired on (now `fail=True` in drc_cases.py). Their
definitions stay in drc_cases_pending_c1b.py only as the record of what Calibre ran (the file is the
verbatim generator); records() leaves them out and nothing checks them there. drc_cases.py is the source.
"""
import json

import reliability
# No `as` aliases and no module objects in variables: baseline_guard.py's scan allows only
# <pending module>.cases / .records / .cases_with_meta (SPEC 0019).
import drc_cases_pending_c1a
import drc_cases_pending_c1b
import drc_cases_pending_c1c

# Rules ported to KLayout since the batch: their fixtures live in drc_cases.py now, so records() leaves
# them out (the GDS names of the rest stay as Calibre ran them).
MOVED_RULES = {'ANT_01', 'ANT_02_1', 'ANT_02_2', 'ANT_02_3', 'ANT_03_1', 'ANT_03_2', 'ANT_03_3', 'ANT_04',
               'ANT_05_1', 'ANT_05_2', 'ANT_06_01', 'ANT_06_02'}

# (group, GDS name Calibre ran) -> fields replaced by the Calibre verdict, and why. The ANT_06 equality
# fixtures C1b 0315/0323 (fail=True, Calibre 124) moved with their rules to drc_cases.py.
CORRECTIONS = {
    ('C1a', '0227-NONSIMPLE-self-touching-vertex.gds'): (
        {'fail': False}, 'Calibre는 꼭짓점 하나로만 닿는 두 사각형을 NONSIMPLE로 보지 않음(경고 0)'),
}


def _decks(group):
    if group == 'C1b':
        return [record['deck'] for record in drc_cases_pending_c1b.records()]
    return None


def records():
    """One dict per pending fixture: group, index (in its group), gds, deck, case, run_case_sha256, correction.

    Fixtures of MOVED_RULES are left out; index and gds stay those of the Calibre batch."""
    result, used = [], set()
    for group, group_cases_of in (('C1a', drc_cases_pending_c1a.cases), ('C1b', drc_cases_pending_c1b.cases),
                                  ('C1c', drc_cases_pending_c1c.cases)):
        # JSON round trip: plain lists and dicts, so the hash and the GDS see the same shapes.
        group_cases, decks = json.loads(json.dumps(group_cases_of())), _decks(group)
        for index, case in enumerate(group_cases):
            if case['rule'] in MOVED_RULES:
                continue
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
