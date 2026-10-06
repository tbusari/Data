from pcmsec.configid import morgan_state_baseline, FrameMap, Placement, diff
from pcmsec.counter_check import CounterCheck
from pcmsec.linkbudget import paper_numbers, fspl_db, LinkBudget


def test_config_hash_sensitive_to_placement_but_not_order():
    a = morgan_state_baseline()
    b = FrameMap(a.bit_rate, a.words_per_minor, a.minors_per_major, a.bits_per_word, a.sync_pattern, a.sfid_word,
                 tuple(reversed(a.placements)))
    assert a.config_hash() == b.config_hash()
    moved = tuple(Placement(p.name, p.word + (1 if p.name == "TEMP4" else 0), p.minor, p.bits, p.msb_first, p.dtype)
                  for p in a.placements)
    c = FrameMap(a.bit_rate, a.words_per_minor, a.minors_per_major, a.bits_per_word, a.sync_pattern, a.sfid_word, moved)
    assert a.config_hash() != c.config_hash()
    assert any("TEMP4" in d for d in diff(a, c))
    assert FrameMap.from_json(a.to_json()).config_hash() == a.config_hash()


def test_counter_check_paper_scenarios():
    cc = CounterCheck()
    for v in range(100):
        cc.feed(v)
    assert cc.consistent and cc.fails == 0
    assert cc.feed(131) == "gap" and cc.dropped_frames == 31      # the paper's delta = 32 event
    cc2 = CounterCheck()
    cc2.feed(5)
    assert cc2.feed(13427) == "gap"                                # the paper's first-frame delta = 13,422 ...
    assert cc2.first_anomaly_index == 1 and not cc2.consistent     # ... is flagged, but is not yet distinguishable
    import random
    rnd = random.Random(3)
    outcomes = [cc2.feed(rnd.getrandbits(16)) for _ in range(50)]  # stale map: the slot holds something else
    assert outcomes.count("pass") < 3 and not cc2.consistent       # skew never re-earns consistency
    cc3 = CounterCheck()
    cc3.feed(65534); cc3.feed(65535); assert cc3.feed(0) == "pass"  # wrap at 2**16


def test_link_budget_matches_manuscript():
    n = paper_numbers()
    assert n["fspl_flight_db"] == 123.2
    assert n["eirp_dbm"] == 35.0
    assert n["rx_power_flight_dbm"] == -83.2
    assert n["epl_test_db"] == 120.6
    assert n["rx_power_test_dbm"] == -80.6
    assert 11.0 <= n["epl_equivalent_range_km"] <= 11.5
    assert -97 <= n["threshold_dbm"] <= -94
    assert 11 <= n["margin_flight_db"] <= 13
    lb = LinkBudget(coding_gain_db=8.8)          # LDPC-class gain, if the option set allows it
    assert lb.margin_db(fspl_db(15288.8, lb.freq_hz)) > 20
