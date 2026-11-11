#!/usr/bin/env python3
"""Test di tools/sync_airbnb.py (solo libreria standard, nessuna rete).

    python3 -m unittest discover -s tools -v
    python3 tools/test_sync_airbnb.py
"""
import contextlib
import email.message
import io
import json
import os
import pathlib
import re
import sys
import tempfile
import unittest
import urllib.error
from datetime import date, datetime, timezone
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import sync_airbnb as sa  # noqa: E402

NOW = datetime(2026, 11, 11, 10, 0, tzinfo=timezone.utc)  # oggi a Roma: 2026-11-11
TODAY = date(2026, 11, 11)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

SECRET_URL_B = "https://www.airbnb.com/calendar/ical/11112222.ics?s=deadbeefcafe0123SECRETB"
SECRET_URL_M = "https://www.airbnb.it/calendar/ical/33334444.ics?s=feedface98765SECRETM"
SECRET_URL_X = "https://admin.booking.com/hotel/hoteladmin/ical.html?t=0badc0ffeeSECRETX"


def ics(*events, crlf=True):
    """Calendario minimale (con VTIMEZONE, come gli export reali) attorno a dei VEVENT."""
    head = [
        "BEGIN:VCALENDAR",
        "PRODID;X-RICAL-TZSOURCE=TZINFO:-//Airbnb Inc//Hosting Calendar 1.0//EN",
        "CALSCALE:GREGORIAN",
        "VERSION:2.0",
        "BEGIN:VTIMEZONE",
        "TZID:Europe/Rome",
        "BEGIN:STANDARD",
        "DTSTART:19701025T030000",
        "TZOFFSETFROM:+0200",
        "TZOFFSETTO:+0100",
        "END:STANDARD",
        "END:VTIMEZONE",
    ]
    body = []
    for event in events:
        body += ["BEGIN:VEVENT"] + [line for line in event.strip("\n").split("\n")] + ["END:VEVENT"]
    nl = "\r\n" if crlf else "\n"
    return nl.join(head + body + ["END:VCALENDAR"]) + nl


def fold(line, width=75):
    """Ripiega una riga come da RFC 5545 (a capo + spazio; ics() trasforma gli a capo in CRLF)."""
    chunks = [line[:width]] + [line[i:i + width - 1] for i in range(width, len(line), width - 1)]
    return "\n ".join(chunks)


RESERVED = "\n".join([
    "DTEND;VALUE=DATE:20261227",
    "DTSTART;VALUE=DATE:2026\n 1220",  # piegata a metà del valore (CRLF + spazio)
    "UID:1418fb94e984-0a1b2c3d4e5f60718293a4b5c6d7e8f9@airbnb.com",
    fold("DESCRIPTION:Reservation URL: https://www.airbnb.com/hosting/reservations/"
         "details/HMQX7Z4K2P\\nPhone Number (Last 4 Digits): 4821"),
    "SUMMARY:Reserved",
])
NOT_AVAILABLE = "\n".join([
    "DTEND;VALUE=DATE:20270115",
    "DTSTART;VALUE=DATE:20270110",
    "UID:7f62b94e984-11aa22bb33cc44dd55ee66ff77889900@airbnb.com",
    "SUMMARY:Airbnb (Not available)",
])


def event(start, end=None, **extra):
    lines = [f"DTSTART;VALUE=DATE:{start}"]
    if end:
        lines.append(f"DTEND;VALUE=DATE:{end}")
    lines += [f"{k}:{v}" for k, v in extra.items()]
    return "\n".join(lines)


def ranges_of(text):
    return sa.parse_ical(text).ranges


class ParseTests(unittest.TestCase):
    def test_value_date_with_folded_lines(self):
        result = sa.parse_ical(ics(RESERVED, NOT_AVAILABLE))
        self.assertEqual(result.ranges, [
            (date(2026, 12, 20), date(2026, 12, 27)),
            (date(2027, 1, 10), date(2027, 1, 15)),
        ])
        self.assertEqual(result.events, 2)
        self.assertIn("2026\r\n 1220", ics(RESERVED))
        self.assertIn("\r\n ", ics(RESERVED).split("DESCRIPTION:")[1])

    def test_unfold_handles_tab_and_bare_lf(self):
        text = ics("DTSTART;VALUE=DA\n\tTE:20261220\nDTEND;VALUE=DATE:2026\n 1222", crlf=False)
        self.assertEqual(ranges_of(text), [(date(2026, 12, 20), date(2026, 12, 22))])

    def test_utc_datetimes(self):
        text = ics(
            "DTSTART:20261220T150000Z\nDTEND:20261223T100000Z",
            # 23:30 UTC del 30/12 = 00:30 del 31/12 a Roma
            "DTSTART:20261230T233000Z\nDTEND:20270102T090000Z",
        )
        self.assertEqual(ranges_of(text), [
            (date(2026, 12, 20), date(2026, 12, 23)),
            (date(2026, 12, 31), date(2027, 1, 2)),
        ])

    def test_tzid_europe_rome(self):
        text = ics("DTSTART;TZID=Europe/Rome:20270105T150000\nDTEND;TZID=Europe/Rome:20270108T100000")
        self.assertEqual(ranges_of(text), [(date(2027, 1, 5), date(2027, 1, 8))])

    @unittest.skipIf(sa.ROME is None or sa.resolve_tzid("America/New_York") is None, "no tz database")
    def test_tzid_other_zone_is_converted_to_rome(self):
        # 20:00 a New York del 10/01 = 02:00 dell'11/01 a Roma
        text = ics('DTSTART;TZID="America/New_York":20270110T200000\n'
                   'DTEND;TZID="America/New_York":20270112T080000')
        self.assertEqual(ranges_of(text), [(date(2027, 1, 11), date(2027, 1, 12))])

    def test_unknown_tzid_keeps_written_date(self):
        text = ics("DTSTART;TZID=W. Europe Standard Time:20270105T150000\n"
                   "DTEND;TZID=W. Europe Standard Time:20270107T100000")
        self.assertEqual(ranges_of(text), [(date(2027, 1, 5), date(2027, 1, 7))])

    def test_missing_dtend_is_one_day(self):
        text = ics(event("20270201"), "DTSTART:20270210T150000Z")
        self.assertEqual(ranges_of(text), [
            (date(2027, 2, 1), date(2027, 2, 2)),
            (date(2027, 2, 10), date(2027, 2, 11)),
        ])

    def test_duration(self):
        self.assertEqual(ranges_of(ics(event("20270301", DURATION="P3D"))),
                         [(date(2027, 3, 1), date(2027, 3, 4))])

    def test_dtend_equal_to_dtstart_counts_one_day(self):
        self.assertEqual(ranges_of(ics(event("20270301", "20270301"))),
                         [(date(2027, 3, 1), date(2027, 3, 2))])

    def test_cancelled_events_ignored(self):
        result = sa.parse_ical(ics(
            event("20261201", "20261205", STATUS="CANCELLED"),
            event("20261210", "20261212", STATUS="cancelled"),
            event("20261215", "20261218", STATUS="CONFIRMED"),
        ))
        self.assertEqual(result.ranges, [(date(2026, 12, 15), date(2026, 12, 18))])
        self.assertEqual(result.cancelled, 2)

    def test_nested_components_do_not_leak(self):
        # il DTSTART della VTIMEZONE (1970) e di un VALARM non diventano prenotazioni
        text = ics("BEGIN:VALARM\nDTSTART;VALUE=DATE:19990101\nTRIGGER:-PT15M\nEND:VALARM\n"
                   + event("20261220", "20261222"))
        self.assertEqual(ranges_of(text), [(date(2026, 12, 20), date(2026, 12, 22))])

    def test_invalid_event_skipped(self):
        result = sa.parse_ical(ics("DTSTART:not-a-date\nDTEND:20261222", "SUMMARY:no dates",
                                   event("20261220", "20261222")))
        self.assertEqual(result.ranges, [(date(2026, 12, 20), date(2026, 12, 22))])
        self.assertEqual(result.invalid, 2)

    def test_empty_calendar(self):
        self.assertEqual(ranges_of(ics()), [])

    def test_not_icalendar(self):
        for text in ("", "<!doctype html><html><body>Error</body></html>"):
            with self.assertRaises(ValueError):
                sa.parse_ical(text)

    def test_quoted_parameter_with_colon(self):
        text = ics('DTSTART;X-NOTE="a:b;c";VALUE=DATE:20261220\nDTEND;VALUE=DATE:20261221')
        self.assertEqual(ranges_of(text), [(date(2026, 12, 20), date(2026, 12, 21))])


class RangeTests(unittest.TestCase):
    def test_merge_overlapping_and_touching(self):
        d = lambda day: date(2026, 12, day)  # noqa: E731
        merged = sa.merge_ranges([(d(18), d(20)), (d(10), d(15)), (d(12), d(18)),
                                  (d(11), d(13)), (d(21), d(22))])
        self.assertEqual(merged, [(d(10), d(20)), (d(21), d(22))])

    def test_past_ranges_dropped_and_current_clipped(self):
        booked = sa.normalize([
            (date(2026, 10, 1), date(2026, 10, 5)),    # passato
            (date(2026, 11, 5), date(2026, 11, 11)),   # check-out oggi: oggi è libero
            (date(2026, 11, 9), date(2026, 11, 14)),   # in corso
            (date(2026, 11, 20), date(2026, 11, 22)),
        ], TODAY)
        self.assertEqual(booked, [["2026-11-11", "2026-11-14"], ["2026-11-20", "2026-11-22"]])

    def test_horizon_18_months(self):
        booked = sa.normalize([
            (date(2028, 5, 1), date(2028, 6, 1)),
            (date(2028, 5, 11), date(2028, 5, 20)),
        ], TODAY)
        self.assertEqual(booked, [["2028-05-01", "2028-05-11"]])

    def test_add_months(self):
        self.assertEqual(sa.add_months(date(2026, 8, 31), 18), date(2028, 2, 29))
        self.assertEqual(sa.add_months(date(2026, 11, 11), 18), date(2028, 5, 11))

    def test_rome_dates(self):
        # 23:30 UTC = 00:30 (inverno) / 01:30 (estate) del giorno dopo a Roma
        self.assertEqual(sa.to_rome_date(datetime(2026, 1, 15, 23, 30, tzinfo=timezone.utc)), date(2026, 1, 16))
        self.assertEqual(sa.to_rome_date(datetime(2026, 7, 15, 21, 30, tzinfo=timezone.utc)), date(2026, 7, 15))
        self.assertEqual(sa.to_rome_date(datetime(2026, 7, 15, 22, 30, tzinfo=timezone.utc)), date(2026, 7, 16))

    def test_rome_fallback_without_tz_database(self):
        with mock.patch.object(sa, "ROME", None):
            self.assertEqual(sa.to_rome_date(datetime(2026, 1, 15, 23, 30, tzinfo=timezone.utc)), date(2026, 1, 16))
            self.assertEqual(sa.to_rome_date(datetime(2026, 7, 15, 21, 30, tzinfo=timezone.utc)), date(2026, 7, 15))
            self.assertEqual(sa.to_rome_date(datetime(2026, 7, 15, 22, 30, tzinfo=timezone.utc)), date(2026, 7, 16))
            # cambio dell'ora 2026: 29 marzo e 25 ottobre, alle 01:00 UTC
            self.assertEqual(sa.to_rome_date(datetime(2026, 3, 28, 22, 30, tzinfo=timezone.utc)), date(2026, 3, 28))
            self.assertEqual(sa.to_rome_date(datetime(2026, 10, 24, 22, 30, tzinfo=timezone.utc)), date(2026, 10, 25))


class ConfigTests(unittest.TestCase):
    def test_env_names(self):
        self.assertEqual(sa.env_name("bilocale"), "AIRBNB_ICAL_BILOCALE")
        self.assertEqual(sa.env_name("casa-nonna"), "AIRBNB_ICAL_CASA_NONNA")

    def test_unit_sources_merge_extra(self):
        env = {"AIRBNB_ICAL_BILOCALE": f"  {SECRET_URL_B}\n",
               "AIRBNB_ICAL_BILOCALE_EXTRA": f"{SECRET_URL_X}\n  {SECRET_URL_B}  https://x.example/c.ics"}
        self.assertEqual(sa.unit_sources("bilocale", env),
                         [SECRET_URL_B, SECRET_URL_X, "https://x.example/c.ics"])
        self.assertEqual(sa.unit_sources("monolocale", {"AIRBNB_ICAL_MONOLOCALE": "  "}), [])

    def test_load_units(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = pathlib.Path(tmp, "site.json")
            site.write_text(json.dumps({"airbnb": {"bilocale": "https://www.airbnb.it/rooms/1",
                                                   "monolocale": ""}}), encoding="utf-8")
            self.assertEqual(sa.load_units(site), ["bilocale", "monolocale"])
            site.write_text(json.dumps({"name": "x"}), encoding="utf-8")
            self.assertEqual(sa.load_units(site), ["bilocale", "monolocale"])
            self.assertEqual(sa.load_units(pathlib.Path(tmp, "missing.json")), ["bilocale", "monolocale"])


class FakeResponse:
    def __init__(self, body, charset="utf-8"):
        self._body = body.encode(charset)
        self.headers = email.message.Message()
        self.headers["Content-Type"] = f"text/calendar; charset={charset}"

    def read(self, n=-1):
        return self._body if n is None or n < 0 else self._body[:n]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOpener:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.requests = []

    def __call__(self, request, timeout=None):
        self.requests.append((request, timeout))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return FakeResponse(outcome)


def http_error(code):
    return urllib.error.HTTPError(SECRET_URL_B, code, "error", email.message.Message(), io.BytesIO(b""))


class FetchTests(unittest.TestCase):
    def test_retries_with_backoff_then_succeeds(self):
        opener = FakeOpener(urllib.error.URLError(TimeoutError()), http_error(503), ics(RESERVED))
        sleeps = []
        text = sa.fetch_ical(SECRET_URL_B, sleep=sleeps.append, urlopen=opener)
        self.assertIn("BEGIN:VCALENDAR", text)
        self.assertEqual(sleeps, [2.0, 4.0])
        request, timeout = opener.requests[0]
        self.assertEqual(timeout, 30)
        self.assertEqual(request.get_header("User-agent"), sa.USER_AGENT)

    def test_gives_up_after_three_attempts_without_leaking_url(self):
        opener = FakeOpener(http_error(503), http_error(502), TimeoutError())
        with self.assertRaises(sa.FetchError) as ctx:
            sa.fetch_ical(SECRET_URL_B, sleep=lambda s: None, urlopen=opener)
        self.assertEqual(len(opener.requests), 3)
        self.assertNotIn("SECRET", str(ctx.exception))
        self.assertNotIn("airbnb", str(ctx.exception))

    def test_client_error_not_retried(self):
        opener = FakeOpener(http_error(404))
        with self.assertRaises(sa.FetchError) as ctx:
            sa.fetch_ical(SECRET_URL_B, sleep=lambda s: None, urlopen=opener)
        self.assertEqual(len(opener.requests), 1)
        self.assertIn("HTTP 404", str(ctx.exception))

    def test_unexpected_errors_do_not_leak_url(self):
        def fetch(url):
            raise ValueError(f"unknown url type: {url!r}")
        stderr = io.StringIO()
        with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "false"}), \
                contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(io.StringIO()):
            data, failures = sa.sync(["bilocale"], {"AIRBNB_ICAL_BILOCALE": SECRET_URL_B},
                                     {"updated": None, "units": {}}, fetch, NOW)
        self.assertEqual(failures, ["bilocale"])
        self.assertIn("ValueError", stderr.getvalue())
        self.assertNotIn("SECRET", stderr.getvalue())

    def test_webcal_and_bad_scheme(self):
        opener = FakeOpener(ics())
        sa.fetch_ical("webcal://example.com/c.ics?token=SECRET", urlopen=opener)
        self.assertEqual(opener.requests[0][0].full_url, "https://example.com/c.ics?token=SECRET")
        with self.assertRaises(sa.FetchError) as ctx:
            sa.fetch_ical("file:///etc/SECRET", urlopen=FakeOpener())
        self.assertNotIn("SECRET", str(ctx.exception))


class SyncTests(unittest.TestCase):
    """Esecuzione completa di main() con download simulati, in una cartella temporanea."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)
        self.out = self.dir / "assets" / "data" / "availability.json"
        self.site = self.dir / "site.json"
        self.site.write_text("{}", encoding="utf-8")
        # niente annotazioni ::warning:: di GitHub Actions dai test
        patcher = mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "false"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def write_previous(self, data, path=None):
        path = path or self.out
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")

    def run_sync(self, env, responses, *extra_args):
        calls = []

        def fetch(url):
            calls.append(url)
            outcome = responses[url]
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome

        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = sa.main(["--out", str(self.out), "--site", str(self.site), *extra_args],
                           environ=env, fetch=fetch, now=NOW)
        text = self.out.read_text(encoding="utf-8")
        self.calls = calls
        self.logs = stdout.getvalue() + stderr.getvalue()
        return code, json.loads(text), text

    def assert_schema(self, data):
        self.assertEqual(set(data), {"updated", "units"})
        for unit, info in data["units"].items():
            self.assertEqual(set(info), {"booked"}, unit)
            for item in info["booked"]:
                self.assertEqual(len(item), 2)
                self.assertTrue(all(DATE_RE.match(x) for x in item), item)
                self.assertLess(item[0], item[1])

    def test_pii_never_published_or_logged(self):
        env = {"AIRBNB_ICAL_BILOCALE": SECRET_URL_B, "AIRBNB_ICAL_MONOLOCALE": SECRET_URL_M}
        code, data, text = self.run_sync(env, {SECRET_URL_B: ics(RESERVED, NOT_AVAILABLE),
                                               SECRET_URL_M: ics(NOT_AVAILABLE)})
        self.assertEqual(code, 0)
        self.assert_schema(data)
        self.assertEqual(data["updated"], "2026-11-11T10:00:00Z")
        self.assertEqual(data["units"]["bilocale"]["booked"],
                         [["2026-12-20", "2026-12-27"], ["2027-01-10", "2027-01-15"]])
        for needle in ("4821", "HMQX7Z4K2P", "Reservation", "Phone", "Reserved", "Not available",
                       "airbnb", "http", "@", "UID", "SUMMARY", "DESCRIPTION", "SECRET",
                       "deadbeef", "1418fb94e984", "11112222"):
            self.assertNotIn(needle, text)
        for needle in ("SECRET", "deadbeef", "feedface", "11112222", "http"):
            self.assertNotIn(needle, self.logs)
        # file leggibile: una coppia di date per riga
        self.assertIn('["2026-12-20", "2026-12-27"]', text)
        self.assertTrue(text.endswith("\n"))

    def test_extra_sources_merged(self):
        env = {"AIRBNB_ICAL_BILOCALE": SECRET_URL_B, "AIRBNB_ICAL_BILOCALE_EXTRA": SECRET_URL_X}
        code, data, _ = self.run_sync(env, {
            SECRET_URL_B: ics(event("20261220", "20261227")),
            SECRET_URL_X: ics(event("20261227", "20261230"), event("20270105", "20270107")),
        })
        self.assertEqual(code, 0)
        self.assertEqual(self.calls, [SECRET_URL_B, SECRET_URL_X])
        self.assertEqual(data["units"], {"bilocale": {"booked": [["2026-12-20", "2026-12-30"],
                                                                 ["2027-01-05", "2027-01-07"]]}})

    def test_failure_keeps_previous_data(self):
        self.write_previous({"updated": "2026-11-10T08:00:00Z", "units": {
            "bilocale": {"booked": [["2026-10-01", "2026-10-03"], ["2026-12-01", "2026-12-05"]]},
            "monolocale": {"booked": [["2026-12-24", "2026-12-26"]]},
        }})
        env = {"AIRBNB_ICAL_BILOCALE": SECRET_URL_B, "AIRBNB_ICAL_MONOLOCALE": SECRET_URL_M}
        responses = {SECRET_URL_B: sa.FetchError("HTTP 503 after 3 attempt(s)"),
                     SECRET_URL_M: ics(event("20270101", "20270104"))}
        code, data, _ = self.run_sync(env, responses)
        self.assertEqual(code, 0)
        self.assert_schema(data)
        self.assertEqual(data["units"]["bilocale"]["booked"], [["2026-12-01", "2026-12-05"]])
        self.assertEqual(data["units"]["monolocale"]["booked"], [["2027-01-01", "2027-01-04"]])
        self.assertEqual(data["updated"], "2026-11-11T10:00:00Z")  # monolocale aggiornato ora
        self.assertIn("bilocale", self.logs)
        self.assertNotIn("SECRET", self.logs)
        code, _, _ = self.run_sync(env, responses, "--strict")
        self.assertEqual(code, 1)

    def test_all_failures_keep_previous_updated(self):
        self.write_previous({"updated": "2026-11-10T08:00:00Z", "units": {
            "bilocale": {"booked": [["2026-12-01", "2026-12-05"]]},
        }})
        env = {"AIRBNB_ICAL_BILOCALE": SECRET_URL_B}
        code, data, _ = self.run_sync(env, {SECRET_URL_B: "<html>Service Unavailable</html>"})
        self.assertEqual(code, 0)
        self.assertEqual(data, {"updated": "2026-11-10T08:00:00Z",
                                "units": {"bilocale": {"booked": [["2026-12-01", "2026-12-05"]]}}})

    def test_partial_failure_merges_previous_and_working_sources(self):
        self.write_previous({"updated": "2026-11-10T08:00:00Z", "units": {
            "bilocale": {"booked": [["2026-12-01", "2026-12-05"]]},
        }})
        env = {"AIRBNB_ICAL_BILOCALE": SECRET_URL_B, "AIRBNB_ICAL_BILOCALE_EXTRA": SECRET_URL_X}
        code, data, _ = self.run_sync(env, {SECRET_URL_B: ics(event("20261220", "20261222")),
                                            SECRET_URL_X: TimeoutError()})
        self.assertEqual(code, 0)
        self.assertEqual(data["units"]["bilocale"]["booked"],
                         [["2026-12-01", "2026-12-05"], ["2026-12-20", "2026-12-22"]])
        self.assertEqual(data["updated"], "2026-11-10T08:00:00Z")

    def test_failure_without_previous_leaves_unit_out(self):
        env = {"AIRBNB_ICAL_BILOCALE": SECRET_URL_B, "AIRBNB_ICAL_MONOLOCALE": SECRET_URL_M}
        code, data, _ = self.run_sync(env, {SECRET_URL_B: sa.FetchError("HTTP 404 after 1 attempt(s)"),
                                            SECRET_URL_M: ics()})
        self.assertEqual(code, 0)
        self.assertEqual(data, {"updated": "2026-11-11T10:00:00Z",
                                "units": {"monolocale": {"booked": []}}})

    def test_previous_flag_used_as_fallback(self):
        # in CI --out è il segnaposto del repository, --previous il file già pubblicato
        self.write_previous({"updated": None, "units": {}})
        published = self.dir / "previous.json"
        self.write_previous({"updated": "2026-11-11T06:23:00Z", "units": {
            "bilocale": {"booked": [["2026-12-01", "2026-12-05"]]}}}, published)
        env = {"AIRBNB_ICAL_BILOCALE": SECRET_URL_B}
        _, data, _ = self.run_sync(env, {SECRET_URL_B: sa.FetchError("HTTP 500 after 3 attempt(s)")},
                                   "--previous", str(published))
        self.assertEqual(data["units"]["bilocale"]["booked"], [["2026-12-01", "2026-12-05"]])
        self.assertEqual(data["updated"], "2026-11-11T06:23:00Z")
        # --previous mancante: si ricade sul file --out
        self.write_previous({"updated": "2026-11-09T06:23:00Z", "units": {
            "bilocale": {"booked": [["2026-12-08", "2026-12-09"]]}}})
        _, data, _ = self.run_sync(env, {SECRET_URL_B: sa.FetchError("HTTP 500 after 3 attempt(s)")},
                                   "--previous", str(self.dir / "missing.json"))
        self.assertEqual(data["units"]["bilocale"]["booked"], [["2026-12-08", "2026-12-09"]])

    def test_malformed_previous_ignored(self):
        self.out.parent.mkdir(parents=True)
        for junk in ("not json", "[]", '{"updated": 5, "units": {"bilocale": {"booked": '
                     '[["2026-12-01"], ["x", "y"], "2026-12-01", ["2026-12-05", "2026-12-01"]]}}}'):
            self.out.write_text(junk, encoding="utf-8")
            code, data, _ = self.run_sync({"AIRBNB_ICAL_BILOCALE": SECRET_URL_B},
                                          {SECRET_URL_B: sa.FetchError("HTTP 500 after 3 attempt(s)")})
            self.assertEqual(code, 0)
            self.assert_schema(data)
            self.assertEqual(data["updated"], None)
            self.assertEqual(data["units"].get("bilocale", {"booked": []})["booked"], [])

    def test_no_urls_configured(self):
        self.write_previous({"updated": "2026-11-10T08:00:00Z", "units": {
            "bilocale": {"booked": [["2026-12-01", "2026-12-05"]]}}})
        for args in ((), ("--strict",)):
            code, data, text = self.run_sync({"AIRBNB_ICAL_BILOCALE": ""}, {}, *args)
            self.assertEqual(code, 0)
            self.assertEqual(data, {"updated": None, "units": {}})
            self.assertEqual(text, '{\n  "updated": null,\n  "units": {}\n}\n')
            self.assertEqual(self.calls, [])

    def test_only_configured_units_listed(self):
        code, data, _ = self.run_sync({"AIRBNB_ICAL_MONOLOCALE": SECRET_URL_M},
                                      {SECRET_URL_M: ics(event("20261201", "20261203"))})
        self.assertEqual(list(data["units"]), ["monolocale"])

    def test_units_from_site_json(self):
        self.site.write_text(json.dumps({"airbnb": {"bilocale": "", "casa-nonna": ""}}), encoding="utf-8")
        env = {"AIRBNB_ICAL_CASA_NONNA": SECRET_URL_X, "AIRBNB_ICAL_MONOLOCALE": SECRET_URL_M}
        _, data, _ = self.run_sync(env, {SECRET_URL_X: ics(event("20261201", "20261203"))})
        self.assertEqual(data["units"], {"casa-nonna": {"booked": [["2026-12-01", "2026-12-03"]]}})


if __name__ == "__main__":
    unittest.main(verbosity=2)
