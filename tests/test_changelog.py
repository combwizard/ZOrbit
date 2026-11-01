"""The changelog reader behind Studio's "What's new". The last test keeps CHANGELOG.md in step with the version: the
release (or Unreleased, while the next one is being written) must have its section there."""
import changelog
import paths

SAMPLE = (
    "# Changelog\r\n"
    "\r\n"
    "Intro that is not a section.\r\n"
    "\r\n"
    "## [Unreleased]\r\n"
    "\r\n"
    "The next release lets you do two things.\r\n"
    "It has one more line in the same paragraph.\r\n"
    "\r\n"
    "A second paragraph.\r\n"
    "\r\n"
    "### Added\r\n"
    "\r\n"
    "- Studio: a first thing that is long enough to wrap onto\r\n"
    "  a second line (#12).\r\n"
    "- A second thing.\r\n"
    "\r\n"
    "### Fixed\r\n"
    "\r\n"
    "- A third thing.\r\n"
    "\r\n"
    "## [0.12.0] - 2026-10-31\r\n"
    "\r\n"
    "### Added\r\n"
    "\r\n"
    "- Old one.\r\n"
    "- Old two.\r\n"
    "- Old three.\r\n"
    "- Old four.\r\n"
    "- Old five.\r\n"
    "- Old six.\r\n"
    "\r\n"
    "## [0.11.0]\r\n"
    "\r\n"
    "- Eleven.\r\n"
    "\r\n"
    "[Unreleased]: https://github.com/combwizard/zorbit/compare/v0.12.0...HEAD\r\n"
    "[0.12.0]: https://github.com/combwizard/zorbit/releases/tag/v0.12.0\r\n"
)


def _log(*versions):
    """A changelog with one section per version, each with one bullet, in the order given."""
    return "".join(f"## [{v}]\n\n- Change in {v}.\n\n" for v in versions)


def _versions(secs):
    return [s["version"] for s in secs]


def test_sections_reads_versions_dates_summaries_and_items():
    secs = changelog.sections(SAMPLE)
    assert _versions(secs) == ["Unreleased", "0.12.0", "0.11.0"]
    unreleased = secs[0]
    assert unreleased["date"] == ""
    assert unreleased["summary"] == ("The next release lets you do two things. It has one more line in the same "
                                     "paragraph.\n\nA second paragraph.")
    assert unreleased["items"] == [
        "Studio: a first thing that is long enough to wrap onto a second line (#12).",
        "A second thing.",
        "A third thing.",
    ]
    assert secs[1]["date"] == "2026-10-31" and secs[1]["summary"] == ""
    assert len(secs[1]["items"]) == 6
    assert secs[2] == {"version": "0.11.0", "date": "", "summary": "", "items": ["Eleven."]}


def test_sections_of_nothing_is_empty():
    assert changelog.sections("") == []
    assert changelog.sections("# Just a title\n") == []


def test_link_references_at_the_end_are_not_text():
    secs = changelog.sections(SAMPLE)
    assert all("https" not in item for s in secs for item in s["items"])
    assert all("https" not in s["summary"] for s in secs)


def test_summary_of_gives_the_paragraphs_or_else_the_first_five_items():
    secs = changelog.sections(SAMPLE)
    assert changelog.summary_of(secs[0]) == {
        "text": ["The next release lets you do two things. It has one more line in the same paragraph.",
                 "A second paragraph."],
        "items": []}
    shown = changelog.summary_of(secs[1])
    assert shown == {"text": [], "items": secs[1]["items"][:5]}
    assert len(shown["items"]) == 5


def test_since_with_nothing_seen_gives_only_the_current_section():
    assert _versions(changelog.since(_log("0.12.0", "0.11.0"), "", "0.12.0")) == ["0.12.0"]


def test_since_gives_the_newer_sections_newest_first_at_most_three():
    text = _log("0.13.0", "0.12.0", "0.11.0", "0.10.0", "0.9.0", "0.8.0")
    assert _versions(changelog.since(text, "0.8.0", "0.12.0")) == ["0.12.0", "0.11.0", "0.10.0"]
    assert _versions(changelog.since(text, "0.9.0", "0.12.0")) == ["0.12.0", "0.11.0", "0.10.0"]
    assert _versions(changelog.since(text, "0.10.0", "0.12.0")) == ["0.12.0", "0.11.0"]


def test_since_is_empty_when_the_current_version_was_seen():
    assert changelog.since(_log("0.12.0", "0.11.0"), "0.12.0", "0.12.0") == []


def test_unreleased_stands_in_for_the_current_version_before_the_bump():
    text = _log("Unreleased", "0.11.0")
    assert _versions(changelog.since(text, "", "0.12.0")) == ["Unreleased"]
    assert _versions(changelog.since(text, "0.11.0", "0.12.0")) == ["Unreleased"]


def test_unreleased_is_left_out_once_the_current_version_has_its_section():
    text = _log("Unreleased", "0.12.0", "0.11.0")
    assert _versions(changelog.since(text, "0.11.0", "0.12.0")) == ["0.12.0"]


def test_read_is_empty_when_the_file_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "CHANGELOG", str(tmp_path / "missing.md"))
    assert changelog.read() == ""
    assert changelog.sections(changelog.read()) == []


def test_the_real_changelog_has_a_section_for_this_version_or_unreleased():
    versions = _versions(changelog.sections(changelog.read()))
    assert paths.VERSION in versions or "Unreleased" in versions, "CHANGELOG.md needs a section for this version"
