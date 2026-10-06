from pcmsec.simulate import run


def test_short_simulation_profile_a():
    r = run(seconds=0.25, profile="A", ber=0.0, dropout_s=0.05)
    assert r["payload_exact"] == r["delivered"] > 0
    assert r["decryptor"]["auth_fail"] == 64           # all injected frames rejected
    assert r["decryptor"]["replay"] == 32              # replayed major frame rejected
    assert r["frames_lost_beyond_dropout"] == 0
    assert r["config_hash_match"] is True
    assert r["transition_stats"]["ciphertext"]["transition_density"] > r["transition_stats"]["plaintext"]["transition_density"]


def test_short_simulation_profile_b_and_skew():
    r = run(seconds=0.25, profile="B", ber=0.0, dropout_s=0.05)
    # profile B releases frames before authentication: the injected frames are delivered as
    # pending and then condemned by the deferred tag of their major frame
    assert r["delivered"] - r["payload_exact"] == r["channel"]["injected"]
    assert r["decryptor"]["replay"] == r["channel"]["replayed"]
    assert r["major_frame_auth"]["auth_fail"] >= 1
    assert r["major_frame_auth"]["authenticated"] >= 5
    s = run(seconds=0.25, profile="A", ber=0.0, dropout_s=0.05, ground_skew_words=1, skew_mode="payload")
    assert s["delivered"] == 0                          # geometry-preserving relocation: nothing decrypts ...
    assert s["config_hash_match"] is False              # ... and the hash names the mismatch
    assert s["counter_check"]["consistent"] is True     # counter word still found: staircase alone is blind here
    t = run(seconds=0.25, profile="A", ber=0.0, dropout_s=0.05, ground_skew_words=1, skew_mode="layout")
    assert t["delivered"] == 0 and t["counter_check"]["consistent"] is False
