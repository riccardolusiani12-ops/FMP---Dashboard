"""
Metric glossary — single source of truth for the definitions of every metric
shown in Team Overview, Match Analysis and Opponent Analysis.

Data layer only (no UI). Entries live in ``registry.py`` (assembled from the
``entries_*`` modules); read them through ``loader.py``. ``ui_inventory.py``
maps every metric label rendered in the dashboard to its registry id.

Python dicts rather than JSON on purpose: the repo-wide ``*.json`` rule in
.gitignore would silently exclude a JSON registry from version control.
"""
