#!/usr/bin/env python3
"""Genera il sito statico di «A spasso con Daisy · Chianti Home».

    pip install jinja2      (una volta sola)
    python3 build.py

Legge  src/*.html (template) + src/site.json + src/content/<lingua>.json
       + src/content/legal/<lingua>.json
e scrive per ogni lingua la home e le pagine privacy/ e cookie/:
index.html, privacy/, cookie/ (IT) · en/... · de/...
I file generati sono HTML/CSS puri: si pubblicano così come sono (GitHub Pages).
"""
import json
import pathlib
import re
import sys

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup, escape

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
    # Prefisso sugli id per evitare collisioni tra più SVG nella stessa pagina
    prefix = re.sub(r"\W", "", pathlib.Path(name).stem) + "-"
    ids = set(re.findall(r'\bid="([^"]+)"', text))
    for i in sorted(ids, key=len, reverse=True):
        text = re.sub(rf'\bid="{re.escape(i)}"', f'id="{prefix}{i}"', text)
        text = re.sub(rf'url\(#{re.escape(i)}\)', f"url(#{prefix}{i})", text)
        text = re.sub(rf'href="#{re.escape(i)}"', f'href="#{prefix}{i}"', text)
    # l'SVG decorativo viene descritto dal contenitore (role="img" + aria-label)
    text = re.sub(r"<title>.*?</title>", "", text, flags=re.S)
    text = re.sub(r'\s(role|aria-labelledby)="[^"]*"', "", text, count=2)
    text = text.replace("<svg ", '<svg aria-hidden="true" focusable="false" ', 1)
    return Markup(text.strip())


# Pagine generate per ogni lingua: (nome, sottocartella, template)
PAGES = [
    ("home", "", "home.html"),
    ("privacy", "privacy/", "legal.html"),
    ("cookie", "cookie/", "legal.html"),
]


def format_date(iso, code):
    """Data dell'ultimo aggiornamento delle pagine legali, nel formato della lingua."""
    y, m, d = iso.split("-")
    return f"{d}.{m}.{y}" if code == "de" else f"{d}/{m}/{y}"


def fill_tokens(value, tokens, todo):
    """Sostituisce %%token%% nei testi legali con i dati di src/site.json (o un segnaposto evidenziato)."""
    if isinstance(value, dict):
        return {k: fill_tokens(v, tokens, todo) for k, v in value.items()}
    if isinstance(value, list):
        return [fill_tokens(v, tokens, todo) for v in value]
    if not isinstance(value, str):
        return value

    def repl(match):
        key = match.group(1)
        if key not in tokens:
            return match.group(0)
        val = tokens[key]
        return escape(val) if val else f'<mark class="todo">[{escape(todo)}]</mark>'

    return re.sub(r"%%(\w+)%%", repl, value)


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
    owner = site.get("owner", {})

    ok = True
    for lang in site["languages"]:
        code = lang["code"]
        content_path = SRC / "content" / f"{code}.json"
        legal_path = SRC / "content" / "legal" / f"{code}.json"
        if not content_path.exists() or not legal_path.exists():
            print(f"! mancano i contenuti per {code}, salto")
            continue
        t = load(content_path)
        updated = format_date(site.get("legal_updated", "2026-01-01"), code)
        tokens = {
            "owner_name": owner.get("name", ""),
            "owner_address": owner.get("address", ""),
            "owner_tax_id": owner.get("vat") or owner.get("tax_id", ""),
            "email": site.get("email", ""),
            "site_url": site.get("base_url", ""),
            "updated": updated,
        }
        legal = load(legal_path)
        lg = fill_tokens(legal, tokens, legal["labels"]["todo"])

        for page, page_path, template_name in PAGES:
            out_rel = lang["path"] + page_path
            root = "../" * out_rel.count("/")
            home = "" if page == "home" else root + lang["path"]
            html = env.get_template(template_name).render(
                t=t, lg=lg, site=site, lang=lang, root=root, home=home,
                page=page, page_path=page_path, photos=photos, updated=updated,
            )

            used = set(re.findall(r'href="#(i-[\w-]+)"', html))
            missing = sorted(used - sprite.keys())
            if missing:
                ok = False
                print(f"! {code}/{page}: icone mancanti nello sprite: {', '.join(missing)}")
            symbols = "".join(sprite[i] for i in sorted(used) if i in sprite)
            sprite_html = (
                '<svg xmlns="http://www.w3.org/2000/svg" class="sprite" aria-hidden="true" focusable="false">'
                f"{symbols}</svg>"
            )
            html = html.replace("<!--ICON_SPRITE-->", sprite_html)
            html = re.sub(r"\n\s*\n+", "\n", html)

            out = ROOT / out_rel / "index.html"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(html, encoding="utf-8")
            print(f"✓ {out.relative_to(ROOT)}  ({len(html.encode('utf-8')) / 1024:.1f} KB, {len(used)} icone)")

    if not photos:
        print("· nessuna foto trovata: uso i segnaposto illustrati")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
