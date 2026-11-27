from os29.governance import (
    CertificationRegistry,
    EvidenceGraph,
    GovernanceRegistry,
    IncidentEngine,
    OrganizationalMemory,
    TrustRegistry,
)


def test_graph_explains_gate():
    g = EvidenceGraph()
    g.link("e", "a", "c", "G1", "d")
    assert g.explain("G1")["status"] == "EVIDENCED"


def test_incident_postmortem():
    i = IncidentEngine()
    assert (
        i.record(
            "I1",
            root_cause="x",
            evidence="e",
            impact="low",
            resolution="r",
            rollback="b",
            prevention="p",
        )["status"]
        == "RECORDED"
    )
    assert i.postmortem("I1")["status"] == "POSTMORTEM_READY"


def test_registries_require_observable_data():
    c = CertificationRegistry()
    assert c.register("OS29", "CERTIFIED", {"source": "tests"})["status"] == "REGISTERED"
    t = TrustRegistry()
    assert t.record("OS29", 1, 0, 0)["status"] == "RECORDED"
    g = GovernanceRegistry()
    assert g.assign("Tracing", "OS29")["status"] == "ASSIGNED"
    assert OrganizationalMemory().remember("p", "c", "s", "e", "r", "i")["status"] == "STORED"
