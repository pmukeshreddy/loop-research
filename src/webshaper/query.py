"""Typed directed KP adaptation: union of conjunctive queries, with event joins.

Execution is closed over independently supported facts. Open-world absence is
unknown; only explicit negative evidence can certify a non-member.
"""
from dataclasses import dataclass
from itertools import permutations

from .models import Bundle, Query
from .storage import dump

PREDICATES = {
    "builds": ("company", "product"),
    "has_funding_event": ("company", "funding_event"),
    "round_type": ("funding_event", "category"),
    "announcement_year": ("funding_event", "year"),
    "announcement_date": ("funding_event", "date"),
    "investor": ("funding_event", "investor"),
    "portfolio_company": ("investor", "company"),
    "founded_by": ("company", "person"),
    "founded_year": ("company", "year"),
    "headquartered_in": ("company", "location"),
    "has_acquisition_event": ("company", "acquisition_event"),
    "acquired_company": ("acquisition_event", "company"),
    "acquisition_date": ("acquisition_event", "date"),
    "product_category": ("product", "category"),
    "has_partnership_event": ("company", "partnership_event"),
    "partner_company": ("partnership_event", "company"),
    "partnership_date": ("partnership_event", "date"),
    "partnership_product": ("partnership_event", "product"),
}
OPERATIONAL = {"round_type", "announcement_year", "announcement_date", "founded_year", "acquisition_date", "partnership_date"}


def values(term):
    return term if isinstance(term, list) else [term]


def variable(term):
    return isinstance(term, str) and term.startswith("?")


def validate_bundle(bundle):
    entities = {e.entity_id: e for e in bundle.entities}
    evidence = {e.evidence_id: e for e in bundle.evidence}
    if len(entities) != len(bundle.entities) or len(evidence) != len(bundle.evidence):
        raise ValueError("duplicate entity/evidence identifier")
    if len({f.claim_id for f in bundle.facts}) != len(bundle.facts):
        raise ValueError("duplicate claim identifier")
    for e in bundle.entities:
        if e.entity_id.startswith("?") or not e.entity_id:
            raise ValueError("entity ID collides with variable syntax")
        if e.resolution_status == "resolved" and not e.identifiers:
            raise ValueError("resolved identity needs a source-backed identifier")
    for f in bundle.facts:
        if f.predicate not in PREDICATES:
            raise ValueError("unknown typed predicate")
        kinds = PREDICATES[f.predicate]
        for node, kind in zip((f.subject_id, f.object_id_or_value), kinds):
            if node not in entities or entities[node].kind != kind:
                raise ValueError("fact type mismatch")
        event_nodes = [n for n in (f.subject_id, f.object_id_or_value) if entities[n].kind.endswith("_event")]
        if f.event_id != (event_nodes[0] if event_nodes else None):
            raise ValueError(f"event_id does not match joined event: claim {f.claim_id}, "
                             f"predicate {f.predicate} ({f.subject_id}, {f.object_id_or_value}); "
                             f"expected event_id={(event_nodes[0] if event_nodes else None)!r}, got {f.event_id!r}")
        if f.valid_time.end and f.valid_time.start and f.valid_time.end < f.valid_time.start:
            raise ValueError("invalid effective date interval")
        for eid in f.evidence_ids:
            if eid not in evidence or evidence[eid].claim_id != f.claim_id:
                raise ValueError("unresolvable fact evidence")


def validate_query(query, bundle):
    entities = {e.entity_id: e for e in bundle.entities}
    for branch in query.branches:
        kinds = {query.target: query.answer_type}
        adjacency = {}
        for atom in branch:
            if atom.predicate not in PREDICATES:
                raise ValueError("unknown typed predicate")
            if not variable(atom.subject):
                raise ValueError("subject must be a bound variable; constant-to-constant constraints are redundant")
            for term, kind in zip((atom.subject, atom.object), PREDICATES[atom.predicate]):
                if isinstance(term, list) and (not term or len(term) != len(set(term)) or any(variable(v) for v in term)):
                    raise ValueError("union must contain distinct constants")
                for node in values(term):
                    if variable(node):
                        if node in kinds and kinds[node] != kind:
                            raise ValueError("variable type mismatch")
                        kinds[node] = kind
                    elif node not in entities or entities[node].kind != kind:
                        raise ValueError("constant type mismatch")
            adjacency.setdefault(atom.subject, set())
            if variable(atom.object):
                adjacency[atom.subject].add(atom.object)
                adjacency.setdefault(atom.object, set()).add(atom.subject)
        seen, todo = set(), [query.target]
        while todo:
            node = todo.pop()
            if node not in seen:
                seen.add(node)
                todo.extend(adjacency.get(node, set()) - seen)
        if set(kinds) - seen or query.target not in adjacency:
            raise ValueError("disconnected answer constraints or unbound target")
        if len(kinds) > 8:
            raise ValueError("query exceeds eight-variable safety bound")


def supported_facts(bundle, *, resolve_conflicts=True):
    entities = {e.entity_id: e for e in bundle.entities}
    ev = {e.evidence_id: e for e in bundle.evidence}
    clean = []
    for f in bundle.facts:
        if (f.resolution_status == "resolved"
                and all(entities[n].resolution_status == "resolved" for n in (f.subject_id, f.object_id_or_value))
                and all(ev[e].support_status == "supported" for e in f.evidence_ids)):
            clean.append(f)
    return without_conflicts(clean) if resolve_conflicts else clean


def without_conflicts(clean):
    conflicts = {(f.subject_id, f.predicate, f.object_id_or_value) for f in clean if any(
        (g.subject_id, g.predicate, g.object_id_or_value) == (f.subject_id, f.predicate, f.object_id_or_value)
        and g.polarity != f.polarity for g in clean)}
    return [f for f in clean if (f.subject_id, f.predicate, f.object_id_or_value) not in conflicts]


def eligible_facts(bundle, sources, cutoff, retrospective=False):
    source_map = {s.source_id: s for s in sources}
    evidence = {e.evidence_id: e for e in bundle.evidence}
    eligible = [f for f in supported_facts(bundle, resolve_conflicts=False)
            if f.valid_time.start is not None and f.valid_time.start <= cutoff
            and (f.valid_time.kind == "event" or f.valid_time.end is None or cutoff <= f.valid_time.end)
            and all((s := source_map.get(evidence[e].source_id)) is not None
                    and s.published_at is not None and (retrospective or s.published_at <= cutoff)
                    for e in f.evidence_ids)]
    return without_conflicts(eligible)


@dataclass
class Result:
    answers: list[str]
    proofs: dict[str, list[str]]


def execute(query: Query, bundle: Bundle, facts=None, bindings=None):
    validate_query(query, bundle)
    facts = supported_facts(bundle) if facts is None else facts
    proof_sets = {}
    for branch in query.branches:
        rows = [(dict(bindings or {}), set())]
        for atom in branch:
            next_rows = []
            for row, proof in rows:
                for fact in facts:
                    if fact.predicate != atom.predicate or fact.polarity != "positive":
                        continue
                    bound = dict(row)
                    for term, node in ((atom.subject, fact.subject_id), (atom.object, fact.object_id_or_value)):
                        if variable(term):
                            if term in bound and bound[term] != node:
                                break
                            bound[term] = node
                        elif node not in values(term):
                            break
                    else:
                        next_rows.append((bound, proof | {fact.claim_id}))
            rows = next_rows
            if len(rows) > 10000:
                raise ValueError("query result intermediate row limit exceeded")
        for row, proof in rows:
            if query.target in row:
                proof_sets.setdefault(row[query.target], set()).update(proof)
    return Result(sorted(proof_sets), {a: sorted(p) for a, p in sorted(proof_sets.items())})


def membership(query, bundle, universe, facts=None):
    facts = supported_facts(bundle) if facts is None else facts
    result = execute(query, bundle, facts)
    decisions = {}
    for candidate in universe:
        if candidate in result.answers:
            decisions[candidate] = {"decision": "included", "claim_ids": result.proofs[candidate]}
            continue
        branch_exclusions = []
        for branch in query.branches:
            exclusion = []
            # Sound, deliberately conservative certificate: a directly rooted
            # condition is explicitly false for ALL members of its union.
            for atom in branch:
                if atom.subject == query.target and not variable(atom.object):
                    negatives = [f for f in facts if f.polarity == "negative" and f.subject_id == candidate
                                 and f.predicate == atom.predicate and f.object_id_or_value in values(atom.object)]
                    if {f.object_id_or_value for f in negatives} == set(values(atom.object)):
                        exclusion = [f.claim_id for f in negatives]
                        break
            branch_exclusions.append(exclusion)
        excluded = all(branch_exclusions)
        decisions[candidate] = {"decision": "excluded" if excluded else "unresolved",
                                "claim_ids": sorted({c for ids in branch_exclusions for c in ids}) if excluded else [],
                                "reason": "explicit negative evidence" if excluded else "absence is not negative evidence"}
    return decisions


def canonical(query):
    branches = []
    # Existential variables have branch-local scope in a union. Canonicalize
    # independently so DNF does not cause factorial growth across branches.
    for branch in query.branches:
        variables = sorted({v for a in branch for t in (a.subject, a.object)
                            for v in values(t) if variable(v)} - {query.target})
        if len(variables) > 7:
            raise ValueError("query exceeds canonicalization variable bound")
        best = None
        for order in permutations(variables):
            mapping = {query.target: "?answer", **{v: f"?v{i}" for i, v in enumerate(order)}}
            atoms = []
            for a in branch:
                obj = sorted(a.object) if isinstance(a.object, list) else mapping.get(a.object, a.object)
                atoms.append([mapping.get(a.subject, a.subject), a.predicate, obj])
            encoded = dump(sorted(atoms, key=dump))
            best = encoded if best is None or encoded < best else best
        branches.append(best)
    return dump([query.answer_type, sorted(branches)])
