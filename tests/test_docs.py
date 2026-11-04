"""The docs are published with MkDocs. It rewrites the paths of Markdown images and links for the page's own URL, but
leaves raw HTML as it is, and `mkdocs build --strict` does not look there either. A raw <img src="images/x.png"> builds
without a word and then breaks on the site, because docs/page.md is published as /docs/page/."""
import glob
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_NOT_HTML = re.compile(r"^[ \t]*(```|~~~).*?^[ \t]*\1\s*$|`[^`\n]*`|<!--.*?-->", re.M | re.S)     # code, comments
_TAG = re.compile(r"""<[a-z][a-z0-9]*\b[^>]*?\b(?:src|href|srcset|poster)\s*=\s*["']?([^"'\s>]+)""", re.I)
_LEAVES_THE_PAGE_ALONE = re.compile(r"[a-z][a-z0-9+.-]*:|#", re.I)     # https:, mailto:, or a place on this page


def _local_html_paths(text):
    return [p for p in _TAG.findall(_NOT_HTML.sub("", text)) if not _LEAVES_THE_PAGE_ALONE.match(p)]


@pytest.mark.parametrize("html, found", [
    ('<p align="center">\n  <img src="images/studio.png" alt="x">\n</p>', ["images/studio.png"]),
    ('<img alt="x" src="../images/studio.png">', ["../images/studio.png"]),
    ('<a class="y" href="install.md">Install</a>', ["install.md"]),
    ('<img src=images/x.png alt="x">', ["images/x.png"]),
    ('<img srcset="images/x.png 2x">', ["images/x.png"]),
    ('<video poster="images/x.png"></video>', ["images/x.png"]),
    ('<img src="https://zorbit.lol/x.png">', []),
    ('<a href="#top">Top</a>', []),
    ('Write `<img src="images/x.png">` in a sentence.', []),
    ('```html\n<img src="images/x.png">\n```', []),
    ('1. A step:\n\n    ```html\n    <img src="images/x.png">\n    ```\n', []),
    ('<!-- <img src="images/x.png"> -->', []),
    ('![The ring](images/ring.png)', []),
])
def test_the_check_finds_local_paths_in_raw_html_only(html, found):
    assert _local_html_paths(html) == found


def test_pages_use_markdown_for_local_pictures_and_links():
    pages = glob.glob(os.path.join(ROOT, "docs", "**", "*.md"), recursive=True)
    assert pages, "no docs pages found"
    bad = {}
    for page in pages:
        with open(page, encoding="utf-8") as f:
            paths = _local_html_paths(f.read())
        if paths:
            bad[os.path.relpath(page, ROOT)] = paths
    assert not bad, f"raw HTML with a local path, which breaks on the site; write it in Markdown: {bad}"
