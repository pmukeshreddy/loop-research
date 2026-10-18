"""Freeze a layer's leaves; replace constants with alpha-renamed exact subqueries."""
from .models import Atom, Query
from .query import OPERATIONAL, execute, values, variable
from .storage import dump


def leaf_constants(query, bundle):
    entities = {e.entity_id: e for e in bundle.entities}
    occurrences, eligible = {}, {}
    for branch in query.branches:
        for atom in branch:
            if variable(atom.object):
                continue
            key = dump(sorted(values(atom.object)))
            occurrences[key] = occurrences.get(key, 0) + 1
            if atom.predicate not in OPERATIONAL and all(
                    entities[c].kind in ("company", "investor", "person", "product", "location")
                    for c in values(atom.object)):
                eligible[key] = atom.object
    # A shared constant is not a degree-one leaf. This conservative rule avoids
    # rewriting a repeated constraint as if it were a new reasoning dependency.
    return [eligible[k] for k in sorted(eligible) if occurrences[k] == 1]


def replace_leaf(parent, leaf, subquery, bundle, facts=None):
    if leaf not in leaf_constants(parent, bundle):
        raise ValueError("ineligible leaf or operational filter")
    expected = sorted(values(leaf))
    intermediate = execute(subquery, bundle, facts).answers
    if intermediate != expected:
        raise ValueError("intermediate_answer_changed")
    if any(c in values(a.object) for c in expected for b in subquery.branches for a in b):
        raise ValueError("subquery leaks original constant")
    existing = {v for b in parent.branches for a in b for t in (a.subject, a.object) for v in values(t) if variable(v)}
    subvars = sorted({v for b in subquery.branches for a in b for t in (a.subject, a.object) for v in values(t) if variable(v)})
    mapping = {}
    for v in subvars:
        i = 0
        while f"?expanded_{i}" in existing:
            i += 1
        mapping[v] = f"?expanded_{i}"
        existing.add(mapping[v])
    added = [[Atom(subject=mapping[a.subject], predicate=a.predicate,
                   object=mapping.get(a.object, a.object) if isinstance(a.object, str) else a.object)
              for a in branch] for branch in subquery.branches]
    branches = []
    for branch in parent.branches:
        contains = any(a.object == leaf for a in branch)
        if not contains:
            branches.append(branch)
            continue
        base = [Atom(subject=a.subject, predicate=a.predicate,
                     object=mapping[subquery.target] if a.object == leaf else a.object) for a in branch]
        for subbranch in added:
            branches.append(base + subbranch)
    expanded = Query(target=parent.target, answer_type=parent.answer_type, branches=branches)
    if execute(expanded, bundle, facts).answers != execute(parent, bundle, facts).answers:
        raise ValueError("final_answer_changed")
    return expanded, intermediate, [a for b in added for a in b]


def ablated(query, added_atoms):
    keys = {dump(a) for a in added_atoms}
    branches = [[a for a in branch if dump(a) not in keys] for branch in query.branches]
    return Query(target=query.target, answer_type=query.answer_type, branches=branches)


def redundant(query, added_atoms, bundle, facts=None):
    return execute(ablated(query, added_atoms), bundle, facts).answers == execute(query, bundle, facts).answers
