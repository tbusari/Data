from pcmsec.frame import FrameFormat, SecurityLayout, SecRecord, MinorFrame, build_minor_frame, PROFILE_A
from pcmsec.tmoip import minor_frame_from_tmoip, tmoip_from_minor_frame


def test_paper_rates():
    f = FrameFormat()
    assert f.minor_rate_hz == 2048
    assert f.bit_rate == 3_276_800
    assert f.minor_bytes == 200


def test_sec_record_roundtrip():
    r = SecRecord(b"sessionX", 0x12345678, 0xCAFEBABE, PROFILE_A, 4, 3, b"\x11" * 8)
    w = r.words()
    assert len(w) == 32 and all(0 <= x < 65536 for x in w)
    assert SecRecord.from_words(w) == r


def test_build_and_bytes():
    f = FrameFormat()
    lay = SecurityLayout()
    fr = build_minor_frame(f, 5, list(range(lay.payload_words(f))), lay, counter_lo=77, sec_word=99)
    assert fr.sync == f.sync_pattern and fr.sfid == 5
    assert MinorFrame.from_bytes(fr.to_bytes()).words == fr.words
    pkt = tmoip_from_minor_frame(fr)
    assert len(pkt) == 232  # the paper's TMoIP payload size
    assert minor_frame_from_tmoip(pkt).words == fr.words


def test_overhead():
    f = FrameFormat()
    assert SecurityLayout(tag_words=4).overhead_fraction(f) == 0.06
    assert SecurityLayout(tag_words=2).overhead_fraction(f) == 0.04
    assert SecurityLayout(tag_words=0).overhead_fraction(f) == 0.02
