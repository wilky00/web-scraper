# ABOUTME: JSON-LD parsing utilities shared by name and address extractors.
# ABOUTME: Parses all <script type="application/ld+json"> blocks from a BeautifulSoup tree.
from __future__ import annotations

import json

from bs4 import BeautifulSoup, Tag


def parse_json_ld_blocks(soup: BeautifulSoup) -> list[dict[str, object]]:
    """Return all JSON-LD objects from the page, flattening @graph arrays."""
    blocks: list[dict[str, object]] = []
    for script in soup.find_all("script", type="application/ld+json"):
        if not isinstance(script, Tag):
            continue
        try:
            data = json.loads(script.get_text() or "")
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    blocks.append(item)
        elif isinstance(data, dict):
            graph = data.get("@graph")
            if isinstance(graph, list):
                for item in graph:
                    if isinstance(item, dict):
                        blocks.append(item)
            else:
                blocks.append(data)
    return blocks
