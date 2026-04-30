"""Bridge: parse a markdown vault and emit a KGNode list as JSON.

Vault format assumptions (generic, not Obsidian-specific):
- Files are .md with YAML frontmatter between opening and closing ---
- Frontmatter keys used: title, aliases, description, tags, category
- Inter-note links use [[Target]] or [[Target|Display]] syntax

Domain inference from tags:
- Tags follow an optional hierarchy: root/sub (e.g. mathematics/probability)
- If root == "mathematics", the sub-segment is used as the domain so that
  math sub-topics resolve to probability, linear_algebra, etc. rather than
  the generic "mathematics" bucket.
- All other tags use the root segment as domain.
- Hyphens are normalised to underscores.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

from core.schemas.kg_schemas import KGNode

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)
_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:\|[^\]]+)?]]")

_UMBRELLA_TAGS = {"mathematics"}


def _domain_from_tags(tags: list[str]) -> str:
    if not tags:
        return ""
    parts = tags[0].split("/")
    root = parts[0].replace("-", "_")
    if root in _UMBRELLA_TAGS and len(parts) > 1:
        return parts[1].replace("-", "_")
    return root


def _parse_note(path: Path, vault_root: Path) -> KGNode | None:
    text = path.read_text(encoding="utf-8")
    fm_match = _FRONTMATTER_RE.match(text)
    if not fm_match:
        return None

    fm = yaml.safe_load(fm_match.group(1)) or {}
    name = fm.get("title") or path.stem
    aliases = fm.get("aliases") or []
    description = fm.get("description") or ""
    tags = fm.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]

    body = text[fm_match.end():]
    related = sorted(set(_WIKILINK_RE.findall(body)))

    return KGNode(
        name=name,
        domain=_domain_from_tags(tags),
        aliases=aliases,
        description=description,
        tags=tags,
        related=related,
        source_path=str(path.relative_to(vault_root)),
    )


def bridge(vault_root: Path, output_path: Path) -> None:
    nodes: list[KGNode] = []
    skipped: list[str] = []

    for md_path in sorted(vault_root.rglob("*.md")):
        node = _parse_note(md_path, vault_root)
        if node is None:
            skipped.append(str(md_path.relative_to(vault_root)))
            continue
        nodes.append(node)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps([node.model_dump() for node in nodes], indent=2)
    )
    print(f"Wrote {len(nodes)} nodes to {output_path}")
    if skipped:
        print(f"Skipped (no frontmatter): {skipped}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: bridge_vault.py <vault_root> <output_json>")
        sys.exit(1)
    bridge(Path(sys.argv[1]), Path(sys.argv[2]))
