#!/usr/bin/env python3
"""Genera il sito statico di «A spasso con Daisy · Chianti Home».

    pip install jinja2      (una volta sola)
    python3 build.py

Legge  src/template.html + src/site.json + src/content/<lingua>.json
e scrive index.html (IT), en/index.html, de/index.html.
I file generati sono HTML/CSS puri: si pubblicano così come sono (GitHub Pages).
"""
import json
import pathlib
import re
import sys

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup

ROOT = pathlib.Path(__file__).resolve().parent
SRC = ROOT / "src"
IMG = ROOT / "assets" / "img"


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_photos():
    """Mappa slug -> metadati foto (da assets/img/photos/credits.json), solo se i file esistono."""
    path = IMG / "photos" / "credits.json"
    if not path.exists():
        return {}
    photos = {}
    for item in load(path):
        slug = item["slug"]
        if not (IMG / "photos" / f"{slug}-1024.webp").exists():
            continue
        item["has_sq"] = (IMG / "photos" / f"{slug}-sq-800.webp").exists()
        photos[slug] = item
    return photos


def load_sprite():
    """Mappa id -> <symbol> dallo sprite delle icone."""
    path = IMG / "icons.svg"
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    symbols = {}
    for match in re.finditer(r"<symbol\b[^>]*\bid=\"([^\"]+)\"[^>]*>.*?</symbol>", text, re.S):
        symbols[match.group(1)] = match.group(0)
    return symbols


def svg_inline(name):
    """Incorpora un'illustrazione SVG direttamente nell'HTML (per animarne le parti via CSS)."""
    path = IMG / "illustrations" / name
    if not path.exists():
        return Markup("")
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"<\?xml[^>]*\?>", "", text)
    text = re.sub(r"<!DOCTYPE[^>]*>", "", text)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    return Markup(text.strip())


def main():
    site = load(SRC / "site.json")
    photos = load_photos()
    sprite = load_sprite()
    env = Environment(
        loader=FileSystemLoader(str(SRC)),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=StrictUndefined,
    )
    env.globals["svg_inline"] = svg_inline
    template = env.get_template("template.html")

    ok = True
    for lang in site["languages"]:
        content_path = SRC / "content" / f"{lang['code']}.json"
        if not content_path.exists():
            print(f"! manca {content_path.relative_to(ROOT)}, salto {lang['code']}")
            continue
        t = load(content_path)
        root = "../" * lang["path"].count("/")
        html = template.render(t=t, site=site, lang=lang, root=root, photos=photos)

        used = set(re.findall(r'href="#(i-[\w-]+)"', html))
        missing = sorted(used - sprite.keys())
        if missing:
            ok = False
            print(f"! {lang['code']}: icone mancanti nello sprite: {', '.join(missing)}")
        symbols = "".join(sprite[i] for i in sorted(used) if i in sprite)
        sprite_html = (
            '<svg xmlns="http://www.w3.org/2000/svg" class="sprite" aria-hidden="true" focusable="false">'
            f"{symbols}</svg>"
        )
        html = html.replace("<!--ICON_SPRITE-->", sprite_html)
        html = re.sub(r"\n\s*\n+", "\n", html)

        out = ROOT / lang["path"] / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        print(f"✓ {out.relative_to(ROOT)}  ({len(html.encode('utf-8')) / 1024:.1f} KB, {len(used)} icone)")

    if not photos:
        print("· nessuna foto trovata: uso i segnaposto illustrati")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
