"""What changed, read from CHANGELOG.md: the sections Studio's "What's new" dialog and Settings button show.

Pure: it reads the text it is given (read() gives the file) and writes nothing. Versions are compared with
paths.version_key, so 0.10.0 comes after 0.9.0.
"""
import re

import paths

MAX_SINCE = 3          # at most this many sections in one "What's new", newest first
SUMMARY_ITEMS = 5      # bullets shown for a section that has no summary paragraph

_HEADING = re.compile(r"## \[([^\]]+)\](?: - (\d{4}-\d{2}-\d{2}))?")
_LINK = re.compile(r"\[[^\]]+\]: ")
_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)\s]+\)")      # [text](url): the dialogs show the text only
_BLOG = re.compile(r"More about this release on the blog: (https://zorbit\.lol/docs/blog/[\w-]+/)")
NOTES_MAX_CHARS = 50_000   # a release body longer than this is cut (GitHub allows 125,000)
NOTES_MAX_ITEMS = 40


def _unlink(text: str) -> str:
    """Markdown links reduced to their text: "[#32](https://...)" becomes "#32"."""
    return _MD_LINK.sub(lambda m: m.group(1), text)


def sections(text: str) -> list[dict]:
    """One dict per `## [version]` heading, in order: {"version", "date", "summary", "items"}.

    "version" is the heading's text ("0.12.0" or "Unreleased") and "date" its date, or "". "summary" is the plain text
    between the heading and the first `###` group or bullet: the lines of a paragraph joined with spaces, paragraphs
    joined with a blank line. "items" are the bullets of every `###` group, each one's wrapped lines joined with
    spaces and its leading "- " removed. Markdown links keep only their text. Link references (`[0.12.0]: ...`) end
    the last section.
    """
    found = []                     # (section, its body lines)
    body = None                    # the lines of the section being read; None between sections
    for raw in (text or "").splitlines():
        line = raw.strip()
        if _LINK.match(line):
            break
        m = _HEADING.fullmatch(line)
        if m:
            body = []
            found.append(({"version": m.group(1), "date": m.group(2) or ""}, body))
        elif line.startswith("## "):
            body = None            # another second-level heading: its lines belong to no section
        elif body is not None:
            body.append(line)
    out = []
    for sec, lines in found:
        summary, items = _body(lines)
        sec["summary"], sec["items"] = _unlink(summary), [_unlink(i) for i in items]
        out.append(sec)
    return out


def release_notes(body, version: str) -> dict:
    """The notes of a GitHub release, for Studio's update dialog: {"summary": [paragraphs], "items": [bullets],
    "blog": url or ""}. The body is the release's CHANGELOG section with what the release workflow puts above it
    (build.yml): the download line, the SHA-256 block (up to 0.23.0) and the blog link. Those are dropped; the blog link is kept as
    "blog". Every bullet is kept, up to NOTES_MAX_ITEMS."""
    lines, fenced, blog = [], False, ""
    for raw in (body if isinstance(body, str) else "")[:NOTES_MAX_CHARS].splitlines():
        line = raw.strip()
        if line.startswith("```"):
            fenced = not fenced
            continue
        m = _BLOG.fullmatch(line)
        if m:
            blog = m.group(1)
            continue
        if fenced or line.startswith("Download **ZOrbitSetup-"):
            continue
        lines.append(line)
    secs = sections(f"## [{version}]\n" + "\n".join(lines))
    sec = secs[0] if secs else {"summary": "", "items": []}
    return {"summary": sec["summary"].split("\n\n") if sec["summary"] else [],
            "items": sec["items"][:NOTES_MAX_ITEMS], "blog": blog}


def _body(lines: list[str]) -> tuple[str, list[str]]:
    """(summary, items) of one section's lines, as sections() describes them."""
    paras, para = [], []          # finished summary paragraphs; the one being read
    items, item = [], None        # finished bullets; the one being read (None outside a bullet)
    in_summary = True             # until the first `###` group or bullet
    for line in lines + [""]:     # the blank line at the end closes what is open
        if not line or line.startswith(("- ", "### ")):
            if para:
                paras.append(" ".join(para))
                para = []
            if item is not None:
                items.append(" ".join(item))
                item = None
        if line.startswith("### "):
            in_summary = False
        elif line.startswith("- "):
            in_summary = False
            item = [line[2:].strip()]
        elif line and item is not None:
            item.append(line)     # a wrapped line of the bullet above
        elif line and in_summary:
            para.append(line)
    return "\n\n".join(paras), items


def summary_of(section: dict) -> dict:
    """What a "What's new" entry shows: {"text": [paragraphs], "items": [bullets]}. A section with a summary gives
    its paragraphs and no bullets; one without gives its first five bullets and no paragraphs."""
    if section.get("summary"):
        return {"text": section["summary"].split("\n\n"), "items": []}
    return {"text": [], "items": list(section.get("items", []))[:SUMMARY_ITEMS]}


def since(text: str, seen: str, current: str) -> list[dict]:
    """The sections for "What's new": those after `seen` and not after `current`, newest first, at most MAX_SINCE.

    A `seen` of "" (or one that is not a version) gives only the section for `current`. "Unreleased" stands in for
    `current` when no section has exactly that version (a checkout run before the release bump).
    """
    cur = paths.version_key(current)
    if cur is None:
        return []
    secs = sections(text)
    stand_in = not any(s["version"] == current for s in secs)
    ranked = []                   # (version, section) for every section that is a release up to current
    for s in secs:
        if s["version"] == "Unreleased":
            key = cur if stand_in else None
        else:
            key = paths.version_key(s["version"])
        if key is not None and key <= cur:
            ranked.append((key, s))
    seen_key = paths.version_key(seen)
    if seen_key is None:
        return [s for key, s in ranked if key == cur]
    ranked = [(key, s) for key, s in ranked if key > seen_key]
    ranked.sort(key=lambda p: p[0], reverse=True)
    return [s for _, s in ranked[:MAX_SINCE]]


def read() -> str:
    """The text of CHANGELOG.md, or "" when it cannot be read."""
    try:
        with open(paths.CHANGELOG, encoding="utf-8-sig") as f:
            return f.read()
    except (OSError, ValueError):
        return ""
