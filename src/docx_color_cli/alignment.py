"""Unique whole-paragraph anchors, then bounded all-optimal-LCS evidence."""

from array import array
from collections import Counter, defaultdict
from dataclasses import dataclass

from .anchors import (
    PARA_ID,
    deleted_mark,
    equivalent_hyperlink_field,
    exact_structural_pair,
    joined_gap,
    plain_subsequence_chain,
    protected_move_offsets,
)
from .extract import eligible_text

MAX_CELLS = 250_000


def unique_subsequence(a, b):
    """All optimal alignments when the COMPLETE target is a source subsequence.

    Earliest/latest embeddings bound every possible origin of each target
    character. Equal bounds force its source in every embedding. No tie-break,
    omitted target character, or markup-driven text removal is permitted.
    """
    if max(len(a), len(b)) > 16_000:
        return None
    earliest, cursor = [], 0
    for char in b:
        while cursor < len(a) and a[cursor] != char:
            cursor += 1
        if cursor == len(a):
            return None
        earliest.append(cursor)
        cursor += 1
    latest, cursor = [], len(a) - 1
    for char in reversed(b):
        while a[cursor] != char:
            cursor -= 1
        latest.append(cursor)
        cursor -= 1
    latest.reverse()
    forced = {
        left: j
        for j, (left, right) in enumerate(zip(earliest, latest, strict=True))
        if left == right
    }
    intervals = defaultdict(list)
    for char, left, right in zip(b, earliest, latest, strict=True):
        intervals[char].append((left, right))
    indices, result = defaultdict(int), []
    for i, char in enumerate(a):
        candidates = intervals[char]
        while indices[char] < len(candidates) and candidates[indices[char]][1] < i:
            indices[char] += 1
        possible = indices[char] < len(candidates) and candidates[indices[char]][0] <= i
        result.append(
            ("ALIGNED", forced[i])
            if i in forced
            else ("AMBIGUOUS" if possible else "UNMAPPED", None)
        )
    return result


@dataclass
class Mapping:
    source: int
    offset: int
    origin: str
    eligible: bool
    status: str = "UNMAPPED"
    evidence: str = "no unique paragraph correspondence"
    target: int | None = None
    target_offset: int | None = None


def unique_lcs(a, b):
    """A character is usable only if every optimal LCS maps it to the same place."""
    n, m = len(a), len(b)
    if (n + 1) * (m + 1) > MAX_CELLS:
        return None
    forward = [array("I", [0]) * (m + 1) for _ in range(n + 1)]
    backward = [array("I", [0]) * (m + 1) for _ in range(n + 1)]
    for i in range(n):
        for j in range(m):
            forward[i + 1][j + 1] = (
                forward[i][j] + 1
                if a[i] == b[j]
                else max(forward[i][j + 1], forward[i + 1][j])
            )
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            backward[i][j] = (
                backward[i + 1][j + 1] + 1
                if a[i] == b[j]
                else max(backward[i + 1][j], backward[i][j + 1])
            )
    length = forward[n][m]
    result = []
    for i in range(n):
        candidates = [
            j
            for j in range(m)
            if a[i] == b[j] and forward[i][j] + 1 + backward[i + 1][j + 1] == length
        ]
        omitted = any(
            forward[i][j] + backward[i + 1][j] == length for j in range(m + 1)
        )
        if len(candidates) == 1 and not omitted:
            result.append(("ALIGNED", candidates[0]))
        else:
            result.append(("AMBIGUOUS" if candidates else "UNMAPPED", None))
    return result


def align(source, accepted, records, *, accepted_xml=None):
    by_key = {r.key: r for r in records.values()}
    mappings = [
        Mapping(i, j, key, eligible_text(by_key[key], p.locations[j][0]))
        for i, p in enumerate(source)
        for j, key in enumerate(p.origins)
        if key is not None
    ]
    by_source = defaultdict(list)
    for mapping in mappings:
        by_source[mapping.source].append(mapping)
        if source[mapping.source].unresolved or not mapping.eligible:
            mapping.status = "UNSUPPORTED"
            mapping.evidence = "unresolved projection or complex insertion"
    groups_a, groups_b = defaultdict(list), defaultdict(list)
    for i, p in enumerate(source):
        groups_a[p.part, p.context].append(i)
    for i, p in enumerate(accepted):
        groups_b[p.part, p.context].append(i)
    exact_pairs = 0
    local_regions = 0
    structural_pairs = 0
    joined_regions = 0
    structural_joins = 0
    move_context_pairs = 0
    move_context_join_regions = 0
    unique_subsequence_regions = 0
    move_protection = protected_move_offsets(source)
    all_target_ids = Counter((p.part, p.node.get(PARA_ID)) for p in accepted)
    for group, aa in groups_a.items():
        bb = groups_b[group]
        ca = Counter(source[i].text for i in aa if source[i].text)
        cb = Counter(accepted[i].text for i in bb if accepted[i].text)
        unique_b = {
            accepted[i].text: j for j, i in enumerate(bb) if cb[accepted[i].text] == 1
        }
        anchors = []
        ids_a = Counter(source[i].node.get(PARA_ID) for i in aa)
        ids_b = Counter(accepted[j].node.get(PARA_ID) for j in bb)
        target_ids = {accepted[j].node.get(PARA_ID): k for k, j in enumerate(bb)}
        for ai, i in enumerate(aa):
            p = source[i]
            if not p.text:
                continue
            ident = p.node.get(PARA_ID)
            unique_id = ident and ids_a[ident] == ids_b[ident] == 1
            structural = unique_id and exact_structural_pair(
                p, accepted[bb[target_ids[ident]]]
            )
            hyperlink_bridge = (
                unique_id
                and not structural
                and equivalent_hyperlink_field(
                    p, accepted[bb[target_ids[ident]]], accepted_xml
                )
            )
            outside_moves = (
                unique_id
                and not structural
                and i in move_protection
                and any(
                    m.eligible and m.offset not in move_protection[i]
                    for m in by_source[i]
                )
                and exact_structural_pair(
                    p, accepted[bb[target_ids[ident]]], allow_moves=True
                )
            )
            if structural or outside_moves or hyperlink_bridge:
                bj = target_ids[ident]
                anchors.append((ai, bj))
                structural_pairs += 1
                move_context_pairs += bool(outside_moves)
                for mapping in by_source[i]:
                    if mapping.eligible:
                        if outside_moves and mapping.offset in move_protection[i]:
                            mapping.evidence = "insertion lies inside a protected move scope; origin remains unresolved"
                            continue
                        mapping.status = "EXACT"
                        mapping.evidence = (
                            "unique paragraph ID; exact complete text and identical HYPERLINK destination/result boundaries"
                            if hyperlink_bridge
                            else "unique paragraph ID, exact complete text and boundaries; ordinary insertion outside protected move scopes"
                            if outside_moves
                            else "unique paragraph ID, exact complete text and identical object boundaries"
                        )
                        mapping.target, mapping.target_offset = bb[bj], mapping.offset
                continue
            if p.unresolved:
                if (
                    i in move_protection
                    and unique_id
                    and p.text != accepted[bb[target_ids[ident]]].text
                ):
                    for mapping in by_source[i]:
                        if mapping.eligible:
                            mapping.evidence = "move paragraph projection differs from accepted text; no deterministic safe correspondence"
                continue
            if ca[p.text] == cb[p.text] == 1:
                bj = unique_b[p.text]
                anchors.append((ai, bj))
                exact_pairs += 1
                for mapping in by_source[i]:
                    if mapping.status != "UNSUPPORTED":
                        mapping.status = "EXACT"
                        mapping.evidence = "unique complete paragraph in identical part and structural context"
                        mapping.target, mapping.target_offset = bb[bj], mapping.offset
            elif cb[p.text] and (ca[p.text] > 1 or cb[p.text] > 1):
                for mapping in by_source[i]:
                    if mapping.status != "UNSUPPORTED":
                        mapping.status = "AMBIGUOUS"
                        mapping.evidence = (
                            "repeated complete paragraph without unique origin"
                        )
        # Local alignment is only allowed inside two order-consistent exact anchors.
        if any(x[1] >= y[1] for x, y in zip(anchors, anchors[1:], strict=False)):
            continue
        for (a0, b0), (a1, b1) in zip(anchors, anchors[1:], strict=False):
            left, right = aa[a0 + 1 : a1], bb[b0 + 1 : b1]
            guarded_gap = False
            source_gap = [source[i] for i in left]
            accepted_gap = [accepted[j] for j in right]
            exact_gap = joined_gap(source_gap, accepted_gap)
            if not exact_gap and any(i in move_protection for i in left):
                guarded_gap = joined_gap(source_gap, accepted_gap, allow_moves=True)
            if (
                left
                and right
                and left == list(range(left[0], left[-1] + 1))
                and right == list(range(right[0], right[-1] + 1))
                and (exact_gap or guarded_gap)
            ):
                destinations = [
                    (j, k) for j in right for k in range(len(accepted[j].text))
                ]
                offset = 0
                for i in left:
                    for mapping in by_source[i]:
                        if mapping.eligible:
                            if guarded_gap and mapping.offset in move_protection.get(
                                i, ()
                            ):
                                mapping.evidence = "insertion lies inside a protected move scope; origin remains unresolved"
                                continue
                            mapping.status = "ALIGNED"
                            mapping.evidence = "two exact anchors; identical bounded text stream and surviving paragraph delimiters"
                            mapping.target, mapping.target_offset = destinations[
                                offset + mapping.offset
                            ]
                    offset += len(source[i].text)
                joined_regions += 1
                move_context_join_regions += bool(guarded_gap)
                continue
            if a1 - a0 != 2 or b1 - b0 != 2:
                continue
            i, j = aa[a0 + 1], bb[b0 + 1]
            if (
                source[i].unresolved
                or not by_source[i]
                or any(m.status == "AMBIGUOUS" for m in by_source[i])
            ):
                continue
            local = unique_lcs(source[i].text, accepted[j].text)
            if local is None:
                for mapping in by_source[i]:
                    if mapping.status != "UNSUPPORTED":
                        mapping.evidence = "bounded local alignment budget exceeded"
                continue
            local_regions += 1
            for mapping in by_source[i]:
                if mapping.status == "UNSUPPORTED":
                    continue
                mapping.status, offset = local[mapping.offset]
                mapping.evidence = (
                    "two exact paragraph anchors; agreement across every optimal LCS"
                )
                if offset is not None:
                    mapping.target, mapping.target_offset = j, offset
        # A surviving unique paragraph ID can bound a deleted-mark chain even
        # when neighboring paragraphs contain unsupported objects. Inspect text
        # and delimiters only; never build accepted XML from the tracked tree.
        for end, i in enumerate(aa):
            ident = source[i].node.get(PARA_ID)
            if (
                not ident
                or ids_a[ident] != 1
                or ids_b[ident] != 1
                or deleted_mark(source[i])
            ):
                continue
            start = end
            while start > 0 and deleted_mark(source[aa[start - 1]]):
                start -= 1
            chain = aa[start : end + 1]
            if (
                (len(chain) < 2 and i not in move_protection)
                or chain != list(range(chain[0], chain[-1] + 1))
                or any(
                    source[k].node.get(PARA_ID)
                    and all_target_ids[source[k].part, source[k].node.get(PARA_ID)]
                    for k in chain[:-1]
                )
                or any(
                    m.status in {"EXACT", "ALIGNED"}
                    for k in chain
                    for m in by_source[k]
                )
            ):
                continue
            j = bb[target_ids[ident]]
            if any(bb[bj] == j and aa[ai] not in chain for ai, bj in anchors):
                continue
            chain_source = [source[k] for k in chain]
            exact_chain = joined_gap(chain_source, [accepted[j]])
            guarded_chain = (
                not exact_chain
                and any(k in move_protection for k in chain)
                and joined_gap(chain_source, [accepted[j]], allow_moves=True)
            )
            if not exact_chain and not guarded_chain:
                if any(k in move_protection for k in chain) and plain_subsequence_chain(
                    chain_source, accepted[j]
                ):
                    local = unique_subsequence(
                        "".join(p.text for p in chain_source), accepted[j].text
                    )
                    if local is not None:
                        offset = 0
                        for k in chain:
                            for mapping in by_source[k]:
                                if not mapping.eligible:
                                    continue
                                if mapping.offset in move_protection.get(k, ()):
                                    mapping.evidence = "insertion lies inside a protected move scope; origin remains unresolved"
                                    continue
                                mapping.status, target_offset = local[
                                    offset + mapping.offset
                                ]
                                mapping.evidence = "unique surviving paragraph ID; complete plain chain; agreement of all target subsequence embeddings"
                                if target_offset is not None:
                                    mapping.target, mapping.target_offset = (
                                        j,
                                        target_offset,
                                    )
                            offset += len(source[k].text)
                        unique_subsequence_regions += 1
                continue
            offset = 0
            for k in chain:
                for mapping in by_source[k]:
                    if mapping.eligible:
                        if guarded_chain and mapping.offset in move_protection.get(
                            k, ()
                        ):
                            mapping.evidence = "insertion lies inside a protected move scope; origin remains unresolved"
                            continue
                        mapping.status = "ALIGNED"
                        mapping.evidence = (
                            "unique surviving paragraph ID; exact bounded deleted-mark text chain; ordinary insertion outside protected move scopes"
                            if guarded_chain
                            else "unique surviving paragraph ID; exact bounded deleted-mark text chain"
                        )
                        mapping.target, mapping.target_offset = (
                            j,
                            offset + mapping.offset,
                        )
                offset += len(source[k].text)
            structural_joins += 1
            move_context_join_regions += bool(guarded_chain)
    return mappings, {
        "exact_paragraph_pairs": exact_pairs,
        "local_alignment_regions": local_regions,
        "structural_paragraph_pairs": structural_pairs,
        "exact_bounded_gap_regions": joined_regions,
        "structural_join_regions": structural_joins,
        "move_context_pairs": move_context_pairs,
        "move_context_join_regions": move_context_join_regions,
        "unique_subsequence_regions": unique_subsequence_regions,
        "max_local_dp_cells": MAX_CELLS,
    }
