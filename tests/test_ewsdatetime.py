import datetime

import dateutil.tz
import pytz
import requests_mock
import warnings
try:
    import zoneinfo
except ImportError:
    from backports import zoneinfo

from exchangelib.errors import UnknownTimeZone, NaiveDateTimeNotAllowed
from exchangelib.ewsdatetime import EWSDateTime, EWSDate, EWSTimeZone, UTC
from exchangelib.winzone import generate_map, CLDR_TO_MS_TIMEZONE_MAP, CLDR_WINZONE_URL, CLDR_WINZONE_TYPE_VERSION, \
    CLDR_WINZONE_OTHER_VERSION
from exchangelib.util import CONNECTION_ERRORS

from .common import TimedTestCase


class EWSDateTimeTest(TimedTestCase):

    def test_super_methods(self):
        tz = EWSTimeZone('Europe/Copenhagen')
        self.assertIsInstance(EWSDateTime.now(), EWSDateTime)
        self.assertIsInstance(EWSDateTime.now(tz=tz), EWSDateTime)
        self.assertIsInstance(EWSDateTime.utcnow(), EWSDateTime)
        self.assertIsInstance(EWSDateTime.fromtimestamp(123456789), EWSDateTime)
        self.assertIsInstance(EWSDateTime.fromtimestamp(123456789, tz=tz), EWSDateTime)
        self.assertIsInstance(EWSDateTime.utcfromtimestamp(123456789), EWSDateTime)

    def test_ewstimezone(self):
        # Test autogenerated translations
        tz = EWSTimeZone('Europe/Copenhagen')
        self.assertIsInstance(tz, EWSTimeZone)
        self.assertEqual(tz.key, 'Europe/Copenhagen')
        self.assertEqual(tz.ms_id, 'Romance Standard Time')
        # self.assertEqual(EWSTimeZone('Europe/Copenhagen').ms_name, '')  # EWS works fine without the ms_name

        # Test localzone()
        tz = EWSTimeZone.localzone()
        self.assertIsInstance(tz, EWSTimeZone)

        # Test common helpers
        tz = EWSTimeZone('UTC')
        self.assertIsInstance(tz, EWSTimeZone)
        self.assertEqual(tz.key, 'UTC')
        self.assertEqual(tz.ms_id, 'UTC')
        tz = EWSTimeZone('GMT')
        self.assertIsInstance(tz, EWSTimeZone)
        self.assertEqual(tz.key, 'GMT')
        self.assertEqual(tz.ms_id, 'UTC')

        # Test mapper contents. Latest map from unicode.org has 394 entries
        self.assertGreater(len(EWSTimeZone.IANA_TO_MS_MAP), 300)
        for k, v in EWSTimeZone.IANA_TO_MS_MAP.items():
            self.assertIsInstance(k, str)
            self.assertIsInstance(v, tuple)
            self.assertEqual(len(v), 2)
            self.assertIsInstance(v[0], str)

        # Test IANA exceptions
        sanitized = list(t for t in zoneinfo.available_timezones() if not t.startswith('SystemV/') and t != 'localtime')
        self.assertEqual(set(sanitized) - set(EWSTimeZone.IANA_TO_MS_MAP), set())

        # Test timezone unknown by ZoneInfo
        with self.assertRaises(UnknownTimeZone) as e:
            EWSTimeZone('UNKNOWN')
        self.assertEqual(e.exception.args[0], 'No time zone found with key UNKNOWN')

        # Test timezone known by IANA but with no Winzone mapping
        with self.assertRaises(UnknownTimeZone) as e:
            del EWSTimeZone.IANA_TO_MS_MAP['Africa/Tripoli']
            EWSTimeZone('Africa/Tripoli')
        self.assertEqual(e.exception.args[0], 'No Windows timezone name found for timezone "Africa/Tripoli"')

        # Test __eq__ with non-EWSTimeZone compare
        self.assertFalse(EWSTimeZone('GMT') == zoneinfo.ZoneInfo('UTC'))

        # Test from_ms_id() with non-standard MS ID
        self.assertEqual(EWSTimeZone('Europe/Copenhagen'), EWSTimeZone.from_ms_id('Europe/Copenhagen'))

    def test_from_timezone(self):
        self.assertEqual(
            EWSTimeZone('Europe/Copenhagen'),
            EWSTimeZone.from_timezone(EWSTimeZone('Europe/Copenhagen'))
        )
        self.assertEqual(
            EWSTimeZone('Europe/Copenhagen'),
            EWSTimeZone.from_timezone(zoneinfo.ZoneInfo('Europe/Copenhagen'))
        )
        self.assertEqual(
            EWSTimeZone('Europe/Copenhagen'),
            EWSTimeZone.from_timezone(dateutil.tz.gettz('Europe/Copenhagen'))
        )
        self.assertEqual(
            EWSTimeZone('Europe/Copenhagen'),
            EWSTimeZone.from_timezone(pytz.timezone('Europe/Copenhagen'))
        )

        self.assertEqual(
            EWSTimeZone('UTC'),
            EWSTimeZone.from_timezone(dateutil.tz.UTC)
        )

    def test_localize(self):
        # Test some corner cases around DST
        tz = EWSTimeZone('Europe/Copenhagen')
        with warnings.catch_warnings():
            # localize() is deprecated but we still want to test it. Silence the DeprecationWarning
            warnings.simplefilter("ignore")
            self.assertEqual(
                str(tz.localize(EWSDateTime(2023, 10, 29, 2, 36, 0), is_dst=False)),
                '2023-10-29 02:36:00+01:00'
            )
            self.assertEqual(
                str(tz.localize(EWSDateTime(2023, 10, 29, 2, 36, 0), is_dst=None)),
                '2023-10-29 02:36:00+02:00'
            )
            self.assertEqual(
                str(tz.localize(EWSDateTime(2023, 10, 29, 2, 36, 0), is_dst=True)),
                '2023-10-29 02:36:00+02:00'
            )
            self.assertEqual(
                str(tz.localize(EWSDateTime(2023, 3, 26, 2, 36, 0), is_dst=False)),
                '2023-03-26 02:36:00+01:00'
            )
            self.assertEqual(
                str(tz.localize(EWSDateTime(2023, 3, 26, 2, 36, 0), is_dst=None)),
                '2023-03-26 02:36:00+01:00'
            )
            self.assertEqual(
                str(tz.localize(EWSDateTime(2023, 3, 26, 2, 36, 0), is_dst=True)),
                '2023-03-26 02:36:00+02:00'
            )

    def test_ewsdatetime(self):
        # Test a static timezone
        tz = EWSTimeZone('Etc/GMT-5')
        dt = EWSDateTime(2000, 1, 2, 3, 4, 5, 678901, tzinfo=tz)
        self.assertIsInstance(dt, EWSDateTime)
        self.assertIsInstance(dt.tzinfo, EWSTimeZone)
        self.assertEqual(dt.tzinfo.ms_id, tz.ms_id)
        self.assertEqual(dt.tzinfo.ms_name, tz.ms_name)
        self.assertEqual(str(dt), '2000-01-02 03:04:05.678901+05:00')
        self.assertEqual(
            repr(dt),
            "EWSDateTime(2000, 1, 2, 3, 4, 5, 678901, tzinfo=EWSTimeZone(key='Etc/GMT-5'))"
        )

        # Test a DST timezone
        tz = EWSTimeZone('Europe/Copenhagen')
        dt = EWSDateTime(2000, 1, 2, 3, 4, 5, 678901, tzinfo=tz)
        self.assertIsInstance(dt, EWSDateTime)
        self.assertIsInstance(dt.tzinfo, EWSTimeZone)
        self.assertEqual(dt.tzinfo.ms_id, tz.ms_id)
        self.assertEqual(dt.tzinfo.ms_name, tz.ms_name)
        self.assertEqual(str(dt), '2000-01-02 03:04:05.678901+01:00')
        self.assertEqual(
            repr(dt),
            "EWSDateTime(2000, 1, 2, 3, 4, 5, 678901, tzinfo=EWSTimeZone(key='Europe/Copenhagen'))"
        )

        # Test from_string
        with self.assertRaises(NaiveDateTimeNotAllowed):
            EWSDateTime.from_string('2000-01-02T03:04:05')
        self.assertEqual(
            EWSDateTime.from_string('2000-01-02T03:04:05+01:00'),
            EWSDateTime(2000, 1, 2, 2, 4, 5, tzinfo=UTC)
        )
        self.assertEqual(
            EWSDateTime.from_string('2000-01-02T03:04:05Z'),
            EWSDateTime(2000, 1, 2, 3, 4, 5, tzinfo=UTC)
        )
        self.assertIsInstance(EWSDateTime.from_string('2000-01-02T03:04:05+01:00'), EWSDateTime)
        self.assertIsInstance(EWSDateTime.from_string('2000-01-02T03:04:05Z'), EWSDateTime)

        # Test addition, subtraction, summertime etc
        self.assertIsInstance(dt + datetime.timedelta(days=1), EWSDateTime)
        self.assertIsInstance(dt - datetime.timedelta(days=1), EWSDateTime)
        self.assertIsInstance(dt - EWSDateTime.now(tz=tz), datetime.timedelta)
        self.assertIsInstance(EWSDateTime.now(tz=tz), EWSDateTime)

        # Test various input for from_datetime()
        self.assertEqual(dt, EWSDateTime.from_datetime(
            datetime.datetime(2000, 1, 2, 3, 4, 5, 678901, tzinfo=EWSTimeZone('Europe/Copenhagen'))
        ))
        self.assertEqual(dt, EWSDateTime.from_datetime(
            datetime.datetime(2000, 1, 2, 3, 4, 5, 678901, tzinfo=zoneinfo.ZoneInfo('Europe/Copenhagen'))
        ))
        self.assertEqual(dt, EWSDateTime.from_datetime(
            datetime.datetime(2000, 1, 2, 3, 4, 5, 678901, tzinfo=dateutil.tz.gettz('Europe/Copenhagen'))
        ))
        self.assertEqual(dt, EWSDateTime.from_datetime(
            datetime.datetime(2000, 1, 2, 3, 4, 5, 678901, tzinfo=pytz.timezone('Europe/Copenhagen'))
        ))

        self.assertEqual(dt.ewsformat(), '2000-01-02T03:04:05.678901+01:00')
        utc_tz = EWSTimeZone('UTC')
        self.assertEqual(dt.astimezone(utc_tz).ewsformat(), '2000-01-02T02:04:05.678901Z')
        # Test summertime
        dt = EWSDateTime(2000, 8, 2, 3, 4, 5, 678901, tzinfo=tz)
        self.assertEqual(dt.astimezone(utc_tz).ewsformat(), '2000-08-02T01:04:05.678901Z')

        # Test in-place add and subtract
        dt = EWSDateTime(2000, 1, 2, 3, 4, 5, tzinfo=tz)
        dt += datetime.timedelta(days=1)
        self.assertIsInstance(dt, EWSDateTime)
        self.assertEqual(dt, EWSDateTime(2000, 1, 3, 3, 4, 5, tzinfo=tz))
        dt = EWSDateTime(2000, 1, 2, 3, 4, 5, tzinfo=tz)
        dt -= datetime.timedelta(days=1)
        self.assertIsInstance(dt, EWSDateTime)
        self.assertEqual(dt, EWSDateTime(2000, 1, 1, 3, 4, 5, tzinfo=tz))

        # Test ewsformat() failure
        dt = EWSDateTime(2000, 1, 2, 3, 4, 5)
        with self.assertRaises(ValueError):
            dt.ewsformat()
        # Test wrong tzinfo type
        with self.assertRaises(ValueError):
            EWSDateTime(2000, 1, 2, 3, 4, 5, tzinfo=pytz.timezone('Europe/Copenhagen'))
        with self.assertRaises(ValueError):
            EWSDateTime.from_datetime(EWSDateTime(2000, 1, 2, 3, 4, 5))

    def test_generate(self):
        try:
            type_version, other_version, tz_map = generate_map()
        except CONNECTION_ERRORS:
            # generate_map() requires access to unicode.org, which may be unavailable. Don't fail test, since this is
            # out of our control.
            return
        self.assertEqual(type_version, CLDR_WINZONE_TYPE_VERSION)
        self.assertEqual(other_version, CLDR_WINZONE_OTHER_VERSION)
        self.assertDictEqual(tz_map, CLDR_TO_MS_TIMEZONE_MAP)

    @requests_mock.mock()
    def test_generate_failure(self, m):
        m.get(CLDR_WINZONE_URL, status_code=500)
        with self.assertRaises(ValueError):
            generate_map()

    def test_ewsdate(self):
        self.assertEqual(EWSDate(2000, 1, 1).ewsformat(), '2000-01-01')
        self.assertEqual(EWSDate.from_string('2000-01-01'), EWSDate(2000, 1, 1))
        self.assertEqual(EWSDate.from_string('2000-01-01Z'), EWSDate(2000, 1, 1))
        self.assertEqual(EWSDate.from_string('2000-01-01+01:00'), EWSDate(2000, 1, 1))
        self.assertEqual(EWSDate.from_string('2000-01-01-01:00'), EWSDate(2000, 1, 1))
        self.assertIsInstance(EWSDate(2000, 1, 2) - EWSDate(2000, 1, 1), datetime.timedelta)
        self.assertIsInstance(EWSDate(2000, 1, 2) + datetime.timedelta(days=1), EWSDate)
        self.assertIsInstance(EWSDate(2000, 1, 2) - datetime.timedelta(days=1), EWSDate)

        # Test in-place add and subtract
        dt = EWSDate(2000, 1, 2)
        dt += datetime.timedelta(days=1)
        self.assertIsInstance(dt, EWSDate)
        self.assertEqual(dt, EWSDate(2000, 1, 3))
        dt = EWSDate(2000, 1, 2)
        dt -= datetime.timedelta(days=1)
        self.assertIsInstance(dt, EWSDate)
        self.assertEqual(dt, EWSDate(2000, 1, 1))

        with self.assertRaises(ValueError):
            EWSDate.from_date(EWSDate(2000, 1, 2))
