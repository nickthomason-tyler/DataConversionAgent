"""Lane 1 — deterministic matching.

Claims a mapping only when normalization produces exactly one candidate from
the section's destination pick list, and (for two-column destinations) the
pair passes the cascade constraint. Everything else is left for the
model-assisted lane or a human. Every claimed value is the byte-exact string
from the pick list, so the conversion tool's exact-match import is safe.

Per-client conventions (e.g. New World Permitting sort-order prefixes that
carry meaning, like 1C- = commercial) are supplied as a token_map rule pack —
a small YAML a consultant confirms once per client.
"""

from __future__ import annotations

import re

from .model import Proposal, Section

# Domain abbreviation expansions common in legacy permitting systems
# (incl. New World Permitting). Deterministic, token-level, applied at the
# strongest normalization level only.
ABBREV = {
    "com": "commercial", "comm": "commercial", "res": "residential",
    "bldg": "building", "bld": "building", "elec": "electrical",
    "mech": "mechanical", "plmb": "plumbing", "plum": "plumbing",
    "demo": "demolition", "add": "addition", "alt": "alteration",
    "insp": "inspection", "cert": "certificate", "occ": "occupancy",
    "lic": "license", "reg": "registration", "irr": "irrigation",
    "pp": "private provider", "rev": "revision", "temp": "temporary",
    "misc": "miscellaneous", "equip": "equipment", "gen": "generator",
}

_PUNCT = re.compile(r"[-_/&.,()+:;]+")
_WS = re.compile(r"\s+")
_ORDER_PREFIX = re.compile(r"^\d+[a-z]{0,4}$")  # sort/code tokens like 1, 1c, 330

LEVELS = {1: "exact", 2: "normalized", 3: "abbrev"}


class Matcher:
    def __init__(self, token_map: dict[str, str] | None = None):
        self.token_map = {**ABBREV, **{k.casefold(): v for k, v in (token_map or {}).items()}}

    def norm(self, value: str, level: int) -> str:
        s = _WS.sub(" ", value.casefold().strip())
        if level >= 2:
            s = _WS.sub(" ", _PUNCT.sub(" ", s)).strip()
        if level >= 3:
            tokens: list[str] = []
            for t in s.split(" "):
                if not t:
                    continue
                if t in self.token_map:
                    tokens.extend(self.token_map[t].split(" "))
                elif _ORDER_PREFIX.match(t):
                    continue  # unmapped sort/code token
                else:
                    tokens.append(t)
            # dedupe (order-preserving) so joined source columns like
            # "1C-ELEC 1COM-ELECTRICAL" collapse to "commercial electrical"
            seen: set[str] = set()
            tokens = [t for t in tokens if not (t in seen or seen.add(t))]
            s = " ".join(tokens)
        return s

    def match_one(self, value: str, candidates: list[str], max_level: int) -> tuple[str, str] | None:
        """Return (candidate, method) when exactly one candidate matches."""
        if not value.strip():
            return None
        for level in range(1, max_level + 1):
            idx: dict[str, list[str]] = {}
            for c in candidates:
                idx.setdefault(self.norm(c, level), []).append(c)
            hits = set(idx.get(self.norm(value, level), []))
            if len(hits) == 1:
                return next(iter(hits)), LEVELS[level]
            if len(hits) > 1:
                return None  # ambiguous; stronger levels only blur further
        return None

    def match_first(self, values: list[str], candidates: list[str],
                    max_level: int) -> tuple[str, str] | None:
        for v in values:
            m = self.match_one(v, candidates, max_level)
            if m:
                return m
        return None

    def match_subset(self, value: str, candidates: list[str]) -> tuple[str, str] | None:
        """Unique candidate whose tokens are a subset of the source tokens.

        Used only on cascade-constrained pools (the qualifier column), where
        the source tuple restates type + qualifier, e.g. source
        "1C-ELEC / 1COM-ELECTRICAL" -> pool candidate "Commercial".
        """
        src_tokens = set(self.norm(value, 3).split())
        if not src_tokens:
            return None
        hits = []
        for c in candidates:
            c_tokens = set(self.norm(c, 3).split())
            if c_tokens and c_tokens <= src_tokens:
                hits.append(c)
        if len(set(hits)) == 1:
            return hits[0], "subset"
        return None


def run(section: Section, max_level: int = 3,
        token_map: dict[str, str] | None = None) -> None:
    """Populate section.proposals with deterministic matches."""
    if not section.dest_lists:
        return
    matcher = Matcher(token_map)
    # Identifier-like sections get exact/case-fold matching only.
    if section.title.lower() in {"users"}:
        max_level = 1

    n_dst = len(section.dst_cols)
    for row in section.rows:
        if any(v.strip() for v in row.existing):
            continue  # already mapped by a human — never overwrite
        src = [v for v in row.values if v]
        if not src:
            continue

        if n_dst == 1:
            m = matcher.match_first([" ".join(src), *src], section.dest_lists[0], max_level)
            if m:
                section.proposals[row.row_idx] = Proposal(
                    dest=(m[0],), method=m[1], confidence=1.0, note=f"auto ({m[1]})")
            continue

        if n_dst == 2 and len(section.dest_lists) >= 2:
            # Column 1: joined leading source columns first, then each column.
            lead = src[:-1] if len(src) > 1 else src
            m1 = matcher.match_first([" ".join(lead), *reversed(src)],
                                     section.dest_lists[0], max_level)
            if not m1:
                continue
            pool = section.cascade.get(m1[0]) or section.dest_lists[1]
            if len(pool) == 1:
                m2 = (pool[0], "cascade-single")  # only one valid pairing exists
            else:
                m2 = (matcher.match_first([src[-1], " ".join(src)], pool, max_level)
                      or matcher.match_subset(" ".join(src), pool))
            if not m2:
                continue
            if section.cascade and m2[0] not in section.cascade.get(m1[0], [m2[0]]):
                continue
            method = m1[1] if m1[1] == m2[1] else f"{m1[1]}+{m2[1]}"
            section.proposals[row.row_idx] = Proposal(
                dest=(m1[0], m2[0]), method=method, confidence=1.0,
                note=f"auto ({method})")


def stats(section: Section) -> dict:
    total = len(section.rows)
    pre = sum(1 for r in section.rows if any(v.strip() for v in r.existing))
    auto = len(section.proposals)
    return {"section": section.key, "rows": total, "premapped": pre,
            "auto": auto, "remaining": total - pre - auto}
