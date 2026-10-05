"""Tests for the publisher audit (src/reporting/publisher_audit.py).

Built on the AD HOC NEWS case: auto-generated stock blurbs restating the GPC
separation under a fresh date every day, which led six consecutive briefs.
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ABQ.src.reporting.publisher_audit import (  # noqa: E402
    audit_publishers, blocked_publishers, format_report, load_register,
    needs_review, record_decision,
)

FARM = [
    ("2026-10-02", "Genuine Parts stock after-hours at EUR 112.60: plus 1.19 percent - AD HOC NEWS"),
    ("2026-10-03", "Genuine Parts stock gains 1.69 percent before Q3 results - AD HOC NEWS"),
    ("2026-10-04", "Genuine Parts stock gains 1.69 percent before Q3 results - AD HOC NEWS"),
    ("2026-10-03", "Genuine Parts names CEO-elect - AD HOC NEWS"),
    ("2026-10-04", "Genuine Parts names CEO-elect - AD HOC NEWS"),
    ("2026-10-04", "Genuine Parts stock costs EUR 113.08 - AD HOC NEWS"),
    ("2026-10-01", "Genuine Parts stock rises 0.4 percent - AD HOC NEWS"),
]
NEWSROOM = [
    ("2026-10-01", "Bank of Canada holds rate at 2.25% - Reuters"),
    ("2026-10-02", "Ontario minimum wage rises to $17.95 - Reuters"),
    ("2026-10-03", "Stellantis to close Brampton plant - Reuters"),
    ("2026-10-04", "Diesel hits record in Canada - Reuters"),
    ("2026-10-04", "GPC names leaders for planned separation - Reuters"),
]


def _records(rows, in_digest=False):
    return [{"date": d, "title": t, "in_digest": in_digest} for d, t in rows]


def _by_name(stats):
    return {s.publisher: s for s in stats}


def test_a_stock_blurb_farm_is_flagged_and_a_newsroom_is_not():
    stats = _by_name(audit_publishers(_records(FARM) + _records(NEWSROOM)))
    farm, newsroom = stats["AD HOC NEWS"], stats["Reuters"]
    assert any(f.startswith("REPUBLISHED") for f in farm.flags)
    assert any(f.startswith("TEMPLATED") for f in farm.flags)
    assert newsroom.flags == []


def test_numbers_are_masked_so_templated_copy_is_recognised():
    """"1.19 percent" and "0.4 percent" are the same template."""
    farm = _by_name(audit_publishers(_records(FARM)))["AD HOC NEWS"]
    assert farm.templated_share >= 0.7


def test_one_title_stored_on_several_days_does_not_count_as_a_template():
    rows = [(f"2026-10-0{i}", "Diesel hits record in Canada - Toronto Star") for i in range(1, 7)]
    s = _by_name(audit_publishers(_records(rows)))["Toronto Star"]
    assert not any(f.startswith("TEMPLATED") for f in s.flags)


def test_influence_alone_never_asks_for_a_decision():
    stats = audit_publishers(_records(NEWSROOM, in_digest=True))
    assert needs_review(stats, {}) == []
    assert "Reuters" in format_report(stats, {}, days=7)  # still visible


def test_titles_without_a_publisher_suffix_are_ignored():
    stats = audit_publishers(_records([("2026-10-04", "Canadian diesel hits record")]))
    assert stats == []


def test_a_decision_removes_the_publisher_from_review_and_blocks_it(tmp_path):
    reg = tmp_path / "publisher_review.json"
    stats = audit_publishers(_records(FARM))
    assert [s.publisher for s in needs_review(stats, load_register(reg))] == ["AD HOC NEWS"]

    record_decision(reg, "AD HOC NEWS", "blocked", "stock blurbs", today=date(2026, 10, 5))
    assert needs_review(stats, load_register(reg)) == []
    assert blocked_publishers(reg) == frozenset({"ad hoc news"})

    # Re-deciding under different casing replaces the entry instead of duplicating it.
    record_decision(reg, "ad hoc news", "allowed", "changed mind")
    assert blocked_publishers(reg) == frozenset()
    assert len(load_register(reg)) == 1


def test_an_invalid_decision_is_refused(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        record_decision(tmp_path / "r.json", "X", "maybe")


def test_an_unreadable_register_blocks_nothing_rather_than_crashing(tmp_path):
    reg = tmp_path / "publisher_review.json"
    reg.write_text("{not json", encoding="utf-8")
    assert blocked_publishers(reg) == frozenset()


# --- ABQ pipeline filter: suffix for Google News, feed name for direct feeds ---

def test_pipeline_reads_the_outlet_the_right_way_for_each_feed_type(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from ABQ.src.analyzers import pipeline as pipeline_mod

    reg = tmp_path / "publisher_review.json"
    record_decision(reg, "AD HOC NEWS", "blocked")
    monkeypatch.setattr(pipeline_mod, "PUBLISHER_REGISTER", reg)

    google = SimpleNamespace(title="Abeilles en declin - AD HOC NEWS",
                             url="https://news.google.com/rss/articles/x", source_url="",
                             source_name="Google News - abeilles")
    # A direct feed whose headline happens to end in " - AD HOC NEWS"-like text
    # is still La Presse: the suffix rule must not apply to it.
    direct = SimpleNamespace(title="Varroa - AD HOC NEWS", url="https://lapresse.ca/a",
                             source_url="https://lapresse.ca/rss", source_name="La Presse")
    kept = pipeline_mod.AnalysisPipeline._filter_blocked_publishers([google, direct])
    assert kept == [direct]
