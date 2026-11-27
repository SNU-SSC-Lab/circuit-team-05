"""Reliability table helpers shared by KLayout's Python and normal Python (stdlib only)."""
import hashlib
import json


def case_sha256(case):
    """Hash a fixture definition; GDS bytes carry timestamps, so golden uses this instead."""
    # json.dumps writes tuples as lists, so tuple and list shapes hash the same.
    text = json.dumps(case, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(text.encode('utf-8')).hexdigest()
