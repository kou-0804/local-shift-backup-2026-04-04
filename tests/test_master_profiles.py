# tests/test_master_profiles.py
import os

from webapp.api.masters.profiles import capture_profile, write_bytes, FileProfile

DATA = "shift_scheduler/data"

EXPECTED = {  # the MEASURED reference table — regression guard
    "技師マスタ_確定版.csv":   (False, "\n",   True),
    "スキルマスタ_確定版.csv":  (False, "\r\n", True),
    "公休数マスタ_確定版.csv":  (False, "\n",   True),
    "勤務場所マスタ_確定版.csv": (False, "\r\n", True),
    "特殊配置ルール_確定版.csv": (False, "\n",   True),
    "業務拡大マスタ_確定版.csv": (False, "\n",   True),
    "夜勤回数_確定版.csv":     (False, "\r\n", True),
    "夜勤スキル一覧.csv":      (False, "\r\n", False),
    "予定申請.csv":           (True,  "\r\n", False),
}


def test_capture_profile_matches_measured_truth():
    for fn, (bom, nl, trail) in EXPECTED.items():
        p = capture_profile(os.path.join(DATA, fn))
        assert (p.has_bom, p.newline, p.trailing_newline) == (bom, nl, trail), fn


def test_write_bytes_round_trips_a_simple_profile():
    p = FileProfile("x", "x.csv", has_bom=False, newline="\n",
                    trailing_newline=True, header_text="a,b", format_json={})
    assert write_bytes([["a", "b"], ["1", "2"]], p) == b"a,b\n1,2\n"


def test_write_bytes_honours_bom_crlf_and_no_trailing():
    p = FileProfile("x", "x.csv", has_bom=True, newline="\r\n",
                    trailing_newline=False, header_text="a,b", format_json={})
    assert write_bytes([["a", "b"], ["1", "2"]], p) == b"\xef\xbb\xbfa,b\r\n1,2"
