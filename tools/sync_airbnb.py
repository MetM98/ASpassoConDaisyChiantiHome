#!/usr/bin/env python3
"""Sincronizza il calendario Airbnb -> assets/data/availability.json.

Gira al momento del deploy (GitHub Actions), non nel browser dei visitatori:
legge gli export iCal privati di Airbnb (ed eventualmente Booking.com) dalle
variabili d'ambiente e pubblica SOLO intervalli di date occupate.

    python3 tools/sync_airbnb.py [--out PATH] [--previous PATH] [--strict]

Variabili d'ambiente, per ogni appartamento (<UNIT> in maiuscolo):
    AIRBNB_ICAL_<UNIT>          URL dell'export iCal di Airbnb
    AIRBNB_ICAL_<UNIT>_EXTRA    altri URL iCal (separati da spazi), es. Booking.com

Gli appartamenti sono le chiavi dell'oggetto "airbnb" in src/site.json
(se presente), altrimenti "bilocale" e "monolocale".

Formato in uscita (intervalli semiaperti [inizio, fine): il giorno di fine,
quello del check-out, resta libero):
    {"updated": "2026-11-11T09:00:00Z" | null,
     "units": {"bilocale": {"booked": [["2026-12-20", "2026-12-27"], ...]}}}

Gli URL contengono un token segreto: non vengono mai stampati. Nel file non
finiscono mai nomi, note, UID, link o numeri di telefono: solo date.

Solo libreria standard, Python 3.9+.
"""
from __future__ import annotations

import argparse
import calendar
import functools
import http.client
import json
import os
import pathlib
import re
import sys
import time as _time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone

try:  # Python 3.9+
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_SITE = ROOT / "src" / "site.json"
DEFAULT_OUT = ROOT / "assets" / "data" / "availability.json"
DEFAULT_UNITS = ("bilocale", "monolocale")

ENV_PREFIX = "AIRBNB_ICAL_"
USER_AGENT = "daisy-calendar-sync/1.0 (static site availability sync)"
TIMEOUT = 30
ATTEMPTS = 3
BACKOFF = 2.0  # secondi: 2, poi 4
MAX_BYTES = 5 * 1024 * 1024
HORIZON_MONTHS = 18
ONE_DAY = timedelta(days=1)


# --------------------------------------------------------------------------
# Fuso orario Europe/Rome (con ripiego se il database dei fusi non c'è)
# --------------------------------------------------------------------------

@functools.lru_cache(maxsize=None)
def _zone(name):
    if ZoneInfo is None or not name:
        return None
    try:
        return ZoneInfo(name)
    except Exception:  # nome sconosciuto, malformato o tzdata assente
        return None


ROME = _zone("Europe/Rome")


def _last_sunday(year, month):
    last = date(year, month, calendar.monthrange(year, month)[1])
    return last - timedelta(days=(last.weekday() - 6) % 7)


def _rome_offset_fallback(utc_naive):
    """Ora legale UE: dall'ultima domenica di marzo all'ultima di ottobre, 01:00 UTC."""
    year = utc_naive.year
    dst_start = datetime.combine(_last_sunday(year, 3), time(1))
    dst_end = datetime.combine(_last_sunday(year, 10), time(1))
    return timedelta(hours=2 if dst_start <= utc_naive < dst_end else 1)


def to_rome_date(value):
    """date -> se stessa; datetime con fuso -> data a Roma; datetime "floating" -> data scritta."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.date()
        if ROME is not None:
            return value.astimezone(ROME).date()
        utc = value.astimezone(timezone.utc).replace(tzinfo=None)
        return (utc + _rome_offset_fallback(utc)).date()
    return value


def resolve_tzid(tzid):
    if not tzid:
        return None
    tzid = tzid.strip().strip('"')
    tz = _zone(tzid)
    if tz is None and "/" in tzid:
        # es. "/mozilla.org/20050126_1/Europe/Rome" -> "Europe/Rome"
        tz = _zone("/".join(tzid.strip("/").split("/")[-2:]))
    return tz


# --------------------------------------------------------------------------
# Parsing iCalendar (RFC 5545), estraendo solo date e stato
# --------------------------------------------------------------------------

_DT_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})(?:T(\d{2})(\d{2})(\d{2})?(Z)?)?$")
_DURATION_RE = re.compile(
    r"^([+-])?P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$"
)


def unfold(text):
    """Righe logiche: CRLF/LF seguiti da spazio o tab continuano la riga precedente."""
    text = text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"\n[ \t]", "", text).split("\n")


def _split_unquoted(text, sep):
    parts, buf, quoted = [], [], False
    for ch in text:
        if ch == '"':
            quoted = not quoted
        if ch == sep and not quoted:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return parts


def parse_content_line(line):
    """'DTSTART;TZID=Europe/Rome:20261220T150000' -> ('DTSTART', {'TZID': 'Europe/Rome'}, '2026...')."""
    quoted = False
    for i, ch in enumerate(line):
        if ch == '"':
            quoted = not quoted
        elif ch == ":" and not quoted:
            head, value = line[:i], line[i + 1:]
            break
    else:
        return None
    parts = _split_unquoted(head, ";")
    name = parts[0].strip().upper().rsplit(".", 1)[-1]
    params = {}
    for part in parts[1:]:
        key, _, val = part.partition("=")
        params[key.strip().upper()] = val.strip().strip('"')
    return name, params, value


def parse_ical_time(value, params):
    """Restituisce una date (VALUE=DATE) o un datetime (con fuso se Z o TZID noto)."""
    raw = value.strip().split(",")[0].replace("-", "").replace(":", "").upper()
    match = _DT_RE.match(raw)
    if not match:
        raise ValueError("unrecognised date value")
    y, mo, d = int(match.group(1)), int(match.group(2)), int(match.group(3))
    if match.group(4) is None or params.get("VALUE", "").upper() == "DATE":
        return date(y, mo, d)
    hh, mm, ss = int(match.group(4)), int(match.group(5)), int(match.group(6) or 0)
    moment = datetime(y, mo, d, hh, mm, min(ss, 59))
    if match.group(7):
        return moment.replace(tzinfo=timezone.utc)
    tz = resolve_tzid(params.get("TZID"))
    return moment.replace(tzinfo=tz) if tz is not None else moment


def parse_duration(value):
    match = _DURATION_RE.match(value.strip().upper())
    if not match or not any(match.groups()[1:]):
        raise ValueError("unrecognised duration")
    weeks, days, hours, minutes, seconds = (int(g or 0) for g in match.groups()[1:])
    delta = timedelta(weeks=weeks, days=days, hours=hours, minutes=minutes, seconds=seconds)
    return -delta if match.group(1) == "-" else delta


class NotICalendar(ValueError):
    """La risposta non è un calendario iCal (es. pagina HTML di errore)."""


@dataclass
class ParseResult:
    ranges: list = field(default_factory=list)  # [(date, date)] semiaperti
    events: int = 0
    cancelled: int = 0
    invalid: int = 0


_KEEP = ("DTSTART", "DTEND", "DURATION", "STATUS")


def parse_ical(text):
    """Estrae gli intervalli occupati da un calendario iCal.

    Si tengono solo DTSTART/DTEND/DURATION/STATUS: SUMMARY, DESCRIPTION, UID ecc.
    non vengono nemmeno letti. Solleva NotICalendar se il testo non è un iCalendar.
    """
    lines = unfold(text)
    if not any(line.strip().upper() == "BEGIN:VCALENDAR" for line in lines):
        raise NotICalendar("response is not an iCalendar document")

    result = ParseResult()
    stack, props, raw_events = [], None, []
    for line in lines:
        if not line.strip():
            continue
        parsed = parse_content_line(line)
        if parsed is None:
            continue
        name, params, value = parsed
        if name == "BEGIN":
            stack.append(value.strip().upper())
            if stack[-1] == "VEVENT":
                props = {}
        elif name == "END":
            comp = value.strip().upper()
            if comp in stack:
                while stack and stack.pop() != comp:
                    pass
            if comp == "VEVENT" and props is not None:
                raw_events.append(props)
                props = None
        elif props is not None and stack and stack[-1] == "VEVENT" and name in _KEEP:
            props.setdefault(name, (params, value))

    for props in raw_events:
        result.events += 1
        status = props.get("STATUS", ({}, ""))[1].strip().upper()
        if status == "CANCELLED":
            result.cancelled += 1
            continue
        try:
            start_raw = parse_ical_time(props["DTSTART"][1], props["DTSTART"][0])
            if "DTEND" in props:
                end_raw = parse_ical_time(props["DTEND"][1], props["DTEND"][0])
            elif "DURATION" in props:
                end_raw = start_raw + parse_duration(props["DURATION"][1])
            else:
                end_raw = None
            start = to_rome_date(start_raw)
            end = to_rome_date(end_raw) if end_raw is not None else start + ONE_DAY
            if end <= start:  # DTEND mancante o incoerente: almeno una notte
                end = start + ONE_DAY
        except (KeyError, ValueError, OverflowError):
            result.invalid += 1
            continue
        result.ranges.append((start, end))
    return result


# --------------------------------------------------------------------------
# Intervalli
# --------------------------------------------------------------------------

def add_months(day, months):
    years, month0 = divmod(day.month - 1 + months, 12)
    year, month = day.year + years, month0 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def merge_ranges(ranges):
    """Ordina e fonde gli intervalli sovrapposti o adiacenti ([a,b) + [b,c) -> [a,c))."""
    merged = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1]:
            if end > merged[-1][1]:
                merged[-1][1] = end
        else:
            merged.append([start, end])
    return [(s, e) for s, e in merged]


def normalize(ranges, today, months=HORIZON_MONTHS):
    """Fonde, scarta il passato, taglia a `months` mesi; restituisce [["YYYY-MM-DD", ...]]."""
    horizon = add_months(today, months)
    out = []
    for start, end in merge_ranges(ranges):
        if end <= today or start >= horizon:
            continue
        out.append([max(start, today).isoformat(), min(end, horizon).isoformat()])
    return out


# --------------------------------------------------------------------------
# Configurazione e dati precedenti
# --------------------------------------------------------------------------

def load_units(site_path=DEFAULT_SITE):
    try:
        with open(site_path, encoding="utf-8") as fh:
            airbnb = json.load(fh).get("airbnb")
    except (OSError, ValueError, AttributeError):
        airbnb = None
    if isinstance(airbnb, dict) and airbnb:
        return [str(key) for key in airbnb]
    if isinstance(airbnb, list) and airbnb and all(isinstance(k, str) for k in airbnb):
        return list(airbnb)
    return list(DEFAULT_UNITS)


def env_name(unit):
    return ENV_PREFIX + re.sub(r"[^A-Za-z0-9]+", "_", unit).strip("_").upper()


def unit_sources(unit, environ):
    """URL configurati per un appartamento: principale + _EXTRA, senza duplicati."""
    name = env_name(unit)
    urls = (environ.get(name) or "").split() + (environ.get(name + "_EXTRA") or "").split()
    return list(dict.fromkeys(urls))


def _parse_iso_date(text):
    if not isinstance(text, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        raise ValueError("bad date")
    return date.fromisoformat(text)


def load_previous(path):
    """Legge un availability.json esistente; ignora file mancanti o malformati."""
    empty = {"updated": None, "units": {}}
    if not path:
        return empty
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return empty
    if not isinstance(data, dict):
        return empty
    updated = data.get("updated")
    try:
        datetime.fromisoformat(str(updated).replace("Z", "+00:00"))
    except ValueError:
        updated = None
    units = {}
    raw_units = data.get("units")
    for unit, info in (raw_units.items() if isinstance(raw_units, dict) else ()):
        booked = info.get("booked") if isinstance(info, dict) else None
        if not isinstance(booked, list):
            continue
        ranges = []
        for item in booked:
            try:
                start, end = (_parse_iso_date(x) for x in item)
            except (TypeError, ValueError):
                continue
            if start < end:
                ranges.append((start, end))
        units[str(unit)] = ranges
    return {"updated": updated if isinstance(updated, str) else None, "units": units}


# --------------------------------------------------------------------------
# Download
# --------------------------------------------------------------------------

class FetchError(Exception):
    """Errore di download: il messaggio non contiene mai l'URL."""


def _describe(exc):
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code}"
    if isinstance(exc, urllib.error.URLError):
        return f"URLError({type(exc.reason).__name__})"
    return type(exc).__name__


def fetch_ical(url, timeout=TIMEOUT, attempts=ATTEMPTS, backoff=BACKOFF,
               sleep=_time.sleep, urlopen=urllib.request.urlopen):
    if url.lower().startswith("webcal://"):
        url = "https://" + url[len("webcal://"):]
    if urllib.parse.urlsplit(url).scheme.lower() not in ("http", "https"):
        raise FetchError("unsupported URL scheme")
    try:
        request = urllib.request.Request(url, headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/calendar, text/plain;q=0.9, */*;q=0.5",
        })
    except ValueError:
        raise FetchError("invalid URL") from None
    reason = "no attempt"
    for attempt in range(1, attempts + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                raw = response.read(MAX_BYTES + 1)
                charset = response.headers.get_content_charset() or "utf-8"
            if len(raw) > MAX_BYTES:
                raise FetchError("response too large")
            try:
                return raw.decode(charset, errors="replace")
            except LookupError:
                return raw.decode("utf-8", errors="replace")
        except FetchError:
            raise
        except urllib.error.HTTPError as exc:
            reason = _describe(exc)
            if 400 <= exc.code < 500 and exc.code not in (408, 425, 429):
                break  # link errato o revocato: inutile riprovare
        except (OSError, http.client.HTTPException, ValueError) as exc:
            reason = _describe(exc)
        if attempt < attempts:
            sleep(backoff * 2 ** (attempt - 1))
    raise FetchError(f"{reason} after {attempt} attempt(s)")


# --------------------------------------------------------------------------
# Sincronizzazione
# --------------------------------------------------------------------------

def _log(message):
    print(message, flush=True)


def _warn(message):
    print(f"warning: {message}", file=sys.stderr, flush=True)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::warning title=Airbnb calendar sync::{message}", flush=True)


def iso_utc(moment):
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sync(units, environ, previous, fetch, now):
    """Restituisce (dati per availability.json, elenco degli appartamenti con errori)."""
    today = to_rome_date(now)
    out_units, failures = {}, []
    configured = fresh = False

    for unit in units:
        urls = unit_sources(unit, environ)
        if not urls:
            _log(f"{unit}: no iCal URL configured ({env_name(unit)}), skipped")
            continue
        configured = True
        ranges, ok, failed, events, cancelled, invalid = [], 0, 0, 0, 0, 0
        for index, url in enumerate(urls, 1):
            try:
                result = parse_ical(fetch(url))
            except Exception as exc:  # qualunque errore: si tengono i dati precedenti
                failed += 1
                # solo i nostri messaggi, che non contengono mai l'URL
                detail = exc if isinstance(exc, (FetchError, NotICalendar)) else type(exc).__name__
                _warn(f"{unit}: source {index}/{len(urls)} failed: {detail}")
                continue
            ok += 1
            ranges += result.ranges
            events += result.events
            cancelled += result.cancelled
            invalid += result.invalid

        if failed == 0:
            fresh = True
            booked = normalize(ranges, today)
        else:
            failures.append(unit)
            prev = previous["units"].get(unit)
            if prev is None and ok == 0:
                _warn(f"{unit}: no data and no previous data, unit left out")
                continue
            # dati precedenti + eventuali sorgenti riuscite: meglio una data in più
            # segnata occupata che una prenotazione che sparisce
            booked = normalize(ranges + (prev or []), today)
            if prev is None:
                _warn(f"{unit}: no previous data, using {ok}/{len(urls)} working source(s) only")
            else:
                _warn(f"{unit}: keeping previous data ({len(prev)} range(s))"
                      + (f" merged with {ok}/{len(urls)} working source(s)" if ok else ""))
        out_units[unit] = {"booked": booked}
        _log(f"{unit}: {ok}/{len(urls)} source(s) ok, {events} event(s) "
             f"({cancelled} cancelled, {invalid} invalid ignored) -> {len(booked)} booked range(s)")

    if not configured:
        return {"updated": None, "units": {}}, failures
    updated = iso_utc(now) if fresh else previous["updated"]
    return {"updated": updated, "units": out_units}, failures


def dumps(data):
    text = json.dumps(data, indent=2, ensure_ascii=False)
    # una coppia di date per riga
    text = re.sub(r'\[\s+("\d{4}-\d{2}-\d{2}"),\s+("\d{4}-\d{2}-\d{2}")\s+\]', r"[\1, \2]", text)
    return text + "\n"


def write_json(path, data):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(dumps(data), encoding="utf-8")
    os.replace(tmp, path)


def main(argv=None, environ=None, fetch=None, now=None):
    parser = argparse.ArgumentParser(description="Sync Airbnb iCal exports into availability.json.")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="output JSON (default: %(default)s)")
    parser.add_argument("--previous", help="earlier availability.json to fall back on "
                        "if a calendar can't be fetched (default: the --out file)")
    parser.add_argument("--site", default=str(DEFAULT_SITE), help="site.json listing the units")
    parser.add_argument("--strict", action="store_true", help="exit 1 if any calendar fails")
    args = parser.parse_args(argv)

    environ = os.environ if environ is None else environ
    fetch = fetch_ical if fetch is None else fetch
    now = datetime.now(timezone.utc) if now is None else now

    # dati precedenti: --previous (in CI: il file già pubblicato), altrimenti --out
    previous = load_previous(args.previous)
    if not previous["units"]:
        previous = load_previous(args.out)

    data, failures = sync(load_units(args.site), environ, previous, fetch, now)
    write_json(args.out, data)
    _log(f"wrote {args.out}: {len(data['units'])} unit(s), updated={data['updated']}")
    if not data["units"] and data["updated"] is None:
        _log("no calendar configured: the site will show 'coming soon'")
    if failures:
        _warn(f"calendar sync failed for: {', '.join(failures)}")
        return 1 if args.strict else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
