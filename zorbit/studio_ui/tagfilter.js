/* The tag filter's match rule, for the Library and the browser. Pure: no DOM, so Node can load it too (tests/js/tag_filter.js does).

   A filter is a set of tag keys and a mode. In "any" mode an item shows when it carries at least one of the tags; in "all" mode,
   when it carries every one. An empty set shows everything. Favourites is a folder, not a chip, so it is never counted as a tag. */
(function (root) {
  'use strict';
  const FAV = 'favourite';

  /* Does an item with these tag keys pass the filter? `tags` is a Set (or array) of the chosen keys. */
  function match(keys, tags, all) {
    const sel = Array.from(tags || []);
    if (!sel.length) return true;
    const has = new Set(keys || []);
    return all ? sel.every(k => has.has(k)) : sel.some(k => has.has(k));
  }

  /* How many items each tag would give next to the chosen ones: a Map of key -> count over the items that pass the filter. For a
     tag already chosen that is the number of items shown. `lists` holds each item's tag keys. */
  function narrowedCounts(lists, tags, all) {
    const out = new Map();
    for (const keys of lists) {
      if (!match(keys, tags, all)) continue;
      for (const k of new Set(keys)) if (k !== FAV) out.set(k, (out.get(k) || 0) + 1);
    }
    return out;
  }

  const ZTagFilter = { FAV, match, narrowedCounts };
  if (root) root.ZTagFilter = ZTagFilter;
  if (typeof module !== 'undefined') module.exports = ZTagFilter;
})(typeof window !== 'undefined' ? window : null);
