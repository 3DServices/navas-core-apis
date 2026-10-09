#!/usr/bin/env python3
"""
fleet_speed_audit.py — how many units have a broken speed_log?

B4 built a plausibility guard, and on the live route it found that device
862846042643919 reports a total of 6.49 km of travel from its speed field on a
day its coordinates moved 782.99 km. 120x out, on densely sampled fixes with
100% speed coverage. That device's speed_log is not noisy, it is wrong.

That matters well beyond stop detection. Anything trusting speed_log is wrong
on that unit: the stop detection B4 just shipped, the "Moving Speed ( KM/H )"
column in trips/excel and trips/pdf, any over-speed alert, any driver-behaviour
figure, and anything Waswa says about how fast a vehicle was going. B3 is about
to propagate the live store into excel and pdf, so knowing WHICH units cannot
be trusted is input to that work, not a side quest.

METHOD, per unit
  1. find the most recent day in the last --days-back that has any fix. One
     cheap call: location_store.fixes(limit=1) walks days newest-first and
     stops at the first row.
  2. read that whole day unpaginated, dedupe OFF.
  3. run stops.speed_is_plausible() and record which bound it used.

WHAT THE VERDICTS MEAN — and the one distinction that matters
  FLAGGED      the integral of speed over time cannot account for the distance
               between the fixes. Strong evidence the speed field is wrong.
  ok           the integral agrees with the distance. A real clean bill.
  INCONCLUSIVE the fixes were too sparse, or speeds too patchy, to integrate,
               so only the max_speed bound could be applied. That bound assumes
               the vehicle held its peak speed for the whole window including
               every hour parked, so passing it means almost nothing. This is
               NOT a pass, and it is counted separately rather than being
               folded into "ok" — reporting one number over two populations
               that mean different things is how you end up with a figure that
               looks reassuring and is not.
  no fixes     nothing in the window to judge.

Read-only: SELECTs the device registry, reads Cassandra partitions, writes
nothing. Optionally writes a CSV with --csv.

Usage:
    python scripts/fleet_speed_audit.py
    python scripts/fleet_speed_audit.py --limit 25 --days-back 14
    python scripts/fleet_speed_audit.py --day 25-09-2026 --csv fleet_speed.csv
"""

import argparse
import csv
import sys
import time
from datetime import date, datetime, timedelta

sys.path.insert(0, '.')

# psycopg2, config and the endpoints package are imported inside main() so
# that --help works in an environment without the database driver installed.


# The Cassandra position store begins here (established in B1: Postgres trips
# end 01-08-2025, Cassandra fixes begin 05-08-2025 — the two stores share no
# day). Nothing can have a fix before this, so a lookback reaching it can say
# "never" and mean it. A shorter lookback cannot, which is why the verdict
# below is named after what was actually checked.
STORE_BEGINS = date(2025, 8, 5)


def full_reach_days():
    """Days from today back to the first day the store could hold anything."""
    return (date.today() - STORE_BEGINS).days + 1


# ──────────────────────────────────────────────────────────────────────────────
# THE FAST LAST-SEEN PATH
#
# The slow path walks one Cassandra partition PER DAY, because
# dll_location_registry_by_record_ts is keyed (data_device_imei,
# local_system_datestamp) and a day is the only safe granularity. For a unit
# silent for 400 days that is ~428 reads, which is where the 73 seconds per
# unit went — NOT the full-day read, so skipping the speed analysis alone
# would barely have helped.
#
# dll_location_registry is keyed on data_device_imei ALONE, so one query can
# reach a unit's whole history. That turns 428 reads into 1.
#
# The catch, and why this is validated rather than trusted: LIMIT 1 returns
# the FIRST row in clustering order. If that order is ascending, LIMIT 1 hands
# back the OLDEST fix and every "last seen" date is silently wrong. A wrong
# answer that looks right is the worst outcome here, so the fast path is
# checked against the slow one on real units before it is adopted, and
# abandoned if they disagree.

FAST_QUERIES = (
    ('ORDER BY record_timestamp DESC',
     'SELECT local_system_datestamp, record_timestamp '
     'FROM dll_location_registry WHERE data_device_imei = ? '
     'ORDER BY record_timestamp DESC LIMIT 1'),
    ('clustering order as stored',
     'SELECT local_system_datestamp, record_timestamp '
     'FROM dll_location_registry WHERE data_device_imei = ? LIMIT 1'),
)


def prepare_fast(session):
    """The first FAST_QUERIES form the cluster will accept, or (None, None)."""
    for label, cql in FAST_QUERIES:
        try:
            return label, session.prepare(cql)
        except Exception:                                 # noqa: BLE001
            continue
    return None, None


def fast_last_seen(session, statement, imei):
    """One partition read. Returns a datestamp string, or None."""
    try:
        rows = list(session.execute(statement, (''.join(str(imei).split()),)))
    except Exception:                                     # noqa: BLE001
        return None
    if not rows:
        return None
    return getattr(rows[0], 'local_system_datestamp', None)


def validate_fast(session, statement, label, units, slow, sample):
    """Agree with the slow walk on `sample` units, or do not use the fast path.

    Picks units from the front of the list and compares. Only units where the
    slow walk finds a date are usable as evidence: two Nones agreeing proves
    nothing about ordering.
    """
    print('   validating the fast path (%s) against the day-by-day walk'
          % label)

    checked = 0
    for imei, _billing in units:
        if checked >= sample:
            break
        slow_day, _reached = slow(imei)
        if not slow_day:
            continue
        fast_day = fast_last_seen(session, statement, imei)
        checked += 1
        agree = (str(fast_day) == str(slow_day))
        print('      %-17s walk=%s  fast=%s  %s'
              % (imei, slow_day, fast_day, 'agree' if agree else 'DISAGREE'))
        if not agree:
            print('')
            print('   The fast path disagrees with the walk, so it is NOT')
            print('   being used. Most likely dll_location_registry clusters')
            print('   ascending, making LIMIT 1 the oldest fix rather than')
            print('   the newest. Falling back to the slow walk.')
            return False

    if checked == 0:
        print('      no unit in the sample had a datable fix, so the fast')
        print('      path could not be validated. Falling back to the walk.')
        return False

    print('      agreed on %d unit(s) -- using the fast path' % checked)
    return True


def fleet(cursor, only_running):
    cursor.execute("SELECT device_imei, device_billing_status "
                   "FROM dll_device_basic_data "
                   "WHERE device_imei IS NOT NULL ORDER BY device_imei")
    rows = [(str(imei).strip(), str(status or '').strip())
            for imei, status in cursor.fetchall() if str(imei).strip()]
    if only_running:
        rows = [r for r in rows if r[1].lower() == 'running']
    return rows


def last_seen(session, imei, max_days_back):
    """The newest day this unit has ANY fix, looking back further than the
    audit window, or None if it has none at all in that reach.

    This exists because a first run reported 22 of 25 billing=running units as
    "no fixes in the window", and that is ambiguous in a way that matters:

      * the unit stopped transmitting on a date  -> an operations problem, and
        the date says how long it has been quiet
      * the unit has NO fixes ever               -> the Postgres registry and
        the Cassandra telemetry disagree about which units exist, which is a
        known hazard here (a Cassandra table named dll_device_basic_data holds
        different rows from the Postgres one)

    Reporting "no fixes" without separating those two would have been a
    finding about nothing. location_store.MAX_DAYS caps one call at 92 days,
    so this walks backwards in chunks.
    """
    from datetime import date as _date
    end = _date.today()
    stepped = 0

    while stepped < max_days_back:
        span = min(90, max_days_back - stepped)
        start = end - timedelta(days=span - 1)
        # A FAILED READ IS NOT AN EMPTY STORE.
        #
        # The first version of this returned None on PositionsUnavailable,
        # and the caller printed that as NEVER SEEN. A 300-unit run then
        # reported 272 units as having never transmitted -- including seven
        # that a 25-unit run minutes earlier had dated precisely (05-08-2026,
        # 14-08-2026, 25-09-2026...). You cannot invent a date from an empty
        # store, so those reads had succeeded once and failed the second time:
        # the session degrades under a long hammering run. 20s per unit versus
        # 83s in the shorter run is the same story in the timings.
        #
        # So a read error is retried, and if it still fails it is RAISED. The
        # caller reports 'read failed'. "I could not look" must never print as
        # "it never existed" -- the same distinction PositionsUnavailable
        # itself exists to protect.
        last_error = None
        for attempt in range(3):
            try:
                found, _t = location_store.fixes(
                    session, imei,
                    start.strftime('%d-%m-%Y'), end.strftime('%d-%m-%Y'),
                    limit=1, dedupe_coordinates=False, newest_first=True)
                last_error = None
                break
            except location_store.PositionsUnavailable as error:
                last_error = error
                time.sleep(1.5 * (attempt + 1))
        else:
            found = None

        if last_error is not None:
            raise last_error

        if found:
            return found[0].get('datestamp'), stepped
        stepped += span
        end = start - timedelta(days=1)

    return None, stepped


def newest_day_with_fixes(session, imei, days_back, forced_day):
    """The most recent day in the window holding at least one fix.

    fixes(limit=1) walks days newest-first and stops at the first row, so this
    is one partition read in the common case, not days_back of them.
    """
    if forced_day:
        return forced_day

    end = date.today()
    start = end - timedelta(days=max(1, days_back) - 1)

    found, _truncated = location_store.fixes(
        session, imei,
        start.strftime('%d-%m-%Y'), end.strftime('%d-%m-%Y'),
        limit=1, dedupe_coordinates=False, newest_first=True)

    if not found:
        return None
    return found[0].get('datestamp')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--days-back', type=int, default=14,
                    help='how far back to look for a day with fixes')
    ap.add_argument('--day', default=None,
                    help='DD-MM-YYYY: audit this exact day for every unit '
                         'instead of each unit\'s own newest day')
    ap.add_argument('--limit', type=int, default=0,
                    help='audit at most this many units (0 = all)')
    ap.add_argument('--all-billing', action='store_true',
                    help='include units whose billing is not "running"')
    ap.add_argument('--csv', default=None, help='also write a CSV here')
    ap.add_argument('--last-seen-only', action='store_true',
                    help='report only when each unit was last seen; skip the '
                         'speed analysis entirely. Uses a single-partition '
                         'query on dll_location_registry when that can be '
                         'validated against the slow walk, which is what makes '
                         'surveying hundreds of units feasible.')
    ap.add_argument('--validate-sample', type=int, default=2, metavar='N',
                    help='units to cross-check the fast path on before '
                         'trusting it (default 2)')
    ap.add_argument('--trace-silent', type=int, default=0, metavar='DAYS',
                    help='when a unit has no fixes in the window, look back '
                         'this many days to find when it was last seen. '
                         '0 skips it. 365 is a reasonable answer to "is this '
                         'unit quiet, or was it never here at all?"')
    args = ap.parse_args()

    import psycopg2
    from config import DB_LINK
    from endpoints import location_store
    from endpoints import stops

    # the two helpers need them too
    globals()['location_store'] = location_store
    globals()['stops'] = stops

    try:
        conn = psycopg2.connect(DB_LINK)
    except Exception as error:                            # noqa: BLE001
        print('could not reach Postgres for the device registry: %s'
              % str(error)[:110])
        return 1

    with conn:
        with conn.cursor() as cursor:
            units = fleet(cursor, not args.all_billing)
    conn.close()

    if args.limit > 0:
        units = units[:args.limit]

    print('%d units to audit%s' % (len(units),
                                   '' if args.all_billing
                                   else ' (billing=running only)'))
    print('window: %s' % (args.day or 'newest day in the last %d'
                          % args.days_back))
    if args.trace_silent > 0:
        reach = full_reach_days()
        if args.trace_silent >= reach:
            print('silent units traced back %d days, which reaches the start '
                  'of the store (%s)'
                  % (args.trace_silent, STORE_BEGINS.strftime('%d-%m-%Y')))
        else:
            print('silent units traced back %d days -- NOT far enough to '
                  'reach the start of the store (%s, %d days back), so a miss '
                  'cannot be read as "never"'
                  % (args.trace_silent, STORE_BEGINS.strftime('%d-%m-%Y'),
                     reach))
    print('')

    from endpoints.devices import get_cassandra_session
    session = get_cassandra_session()

    if session is None:
        print('no Cassandra session — cannot read any fixes')
        return 1

    rows = []
    t_start = time.time()

    # ---------------------------------------------------------------- 1. mode
    if args.last_seen_only:
        reach = args.trace_silent if args.trace_silent > 0 else full_reach_days()

        def slow(imei):
            return last_seen(session, imei, reach)

        label, statement = prepare_fast(session)
        use_fast = False

        if statement is not None:
            use_fast = validate_fast(session, statement, label, units, slow,
                                     max(1, args.validate_sample))
        else:
            print('   dll_location_registry will not accept either fast query;'
                  ' using the day-by-day walk')

        print('')

        for index, (imei, billing) in enumerate(units, 1):
            line = {'imei': imei, 'billing': billing, 'day': '', 'verdict': '',
                    'basis': 'last-seen-only', 'fixes': 0, 'travelled_km': '',
                    'speed_claims_km': '', 'ratio': '', 'median_gap_s': '',
                    'coverage': '', 'note': ''}

            failed = None
            try:
                if use_fast:
                    day = fast_last_seen(session, statement, imei)
                    reached = reach
                else:
                    day, reached = slow(imei)
            except Exception as error:                    # noqa: BLE001
                day, reached, failed = None, 0, error

            if failed is not None:
                line['verdict'] = 'READ FAILED'
                line['note'] = str(failed)[:70]
                rows.append(line)
                print('   %3d/%d  %-17s READ FAILED   %s'
                      % (index, len(units), imei, line['note']))
                continue

            if day:
                line['day'] = day
                # "active" means a fix inside the audit window, not merely ever
                try:
                    seen_on = datetime.strptime(str(day), '%d-%m-%Y').date()
                    age = (date.today() - seen_on).days
                except (TypeError, ValueError):
                    seen_on, age = None, None

                if age is not None and age <= args.days_back:
                    line['verdict'] = 'REPORTING'
                else:
                    line['verdict'] = 'SILENT'
                line['note'] = ('last fix %s%s'
                                % (day, '' if age is None
                                   else ' (%d days ago)' % age))
            else:
                covers_store = reach >= full_reach_days()
                line['verdict'] = ('NEVER SEEN' if covers_store
                                   else 'NO FIX IN %dd' % reach)
                line['note'] = ('no fix in the store at all' if covers_store
                                else 'no fix in %d days; store begins %s, so '
                                     'this does NOT mean never'
                                     % (reach,
                                        STORE_BEGINS.strftime('%d-%m-%Y')))

            rows.append(line)
            print('   %3d/%d  %-17s %-13s %s'
                  % (index, len(units), imei, line['verdict'], line['note']))

        took = time.time() - t_start
        reporting = [r for r in rows if r['verdict'] == 'REPORTING']
        silent = [r for r in rows if r['verdict'] == 'SILENT']
        never = [r for r in rows if r['verdict'] == 'NEVER SEEN']
        unreached = [r for r in rows if str(r['verdict']).startswith('NO FIX IN')]
        failures = [r for r in rows if r['verdict'] == 'READ FAILED']

        print('')
        print('=' * 74)
        print('   %d units, last-seen only, in %.0fs (%s path)'
              % (len(rows), took, 'fast' if use_fast else 'slow walk'))
        print('=' * 74)
        print('   REPORTING    a fix within %d days                %4d'
              % (args.days_back, len(reporting)))
        print('   SILENT       reported once, not lately           %4d'
              % len(silent))
        print('   NEVER SEEN   no fix anywhere in the store        %4d'
              % len(never))
        if unreached:
            print('   NO FIX IN Nd  lookback did not reach the store %4d'
                  % len(unreached))
        print('   READ FAILED  could not look -- NOT a verdict       %4d'
              % len(failures))

        if failures:
            print('')
            print('   !! %d of %d units could not be read. Those are NOT'
                  % (len(failures), len(rows)))
            print('      "never seen" and must not be counted as such. The')
            print('      Cassandra session degrades over a long run, so a')
            print('      wide survey should be taken in batches -- use')
            print('      --limit with a starting offset, or re-run the failed')
            print('      IMEIs from the CSV.')

        if rows and not failures:
            print('')
            print('   %.0f%% of these units are not reporting.'
                  % (100.0 * (len(silent) + len(never) + len(unreached))
                     / len(rows)))
        elif rows:
            resolved = len(rows) - len(failures)
            if resolved:
                print('')
                print('   Of the %d units actually resolved, %.0f%% are not'
                      % (resolved,
                         100.0 * (len(silent) + len(never) + len(unreached))
                         / resolved))
                print('   reporting. The %d unread units are excluded, not'
                      % len(failures))
                print('   assumed either way.')

        # ── the clustering question this mode exists to answer
        #
        # BY EXACT DATE, not by month. A first version bucketed by month and
        # averaged away the actual signal: four units last reported on
        # 09-09-2026 -- the SAME CALENDAR DAY -- which showed up as an
        # unremarkable "2026-09: 4". Devices failing independently (flat
        # battery, cut wire, vehicle sold) do not share an exact last-seen
        # date. Units sharing one did not fail; something stopped them.
        by_day = {}
        for r in silent:
            key = str(r['day'])
            by_day.setdefault(key, []).append(r['imei'])

        shared = {day: imeis for day, imeis in by_day.items() if len(imeis) > 1}

        if failures:
            print('')
            print('   Date clustering is withheld: with %d unread units the'
                  % len(failures))
            print('   silent set is incomplete, and a cluster\'s size would')
            print('   be an artefact of which reads happened to succeed.')
            if shared:
                print('')
                print('   (For what it is worth, %d date(s) in the resolved'
                      % len(shared))
                print('    set are already shared by more than one unit --')
                print('    worth confirming on a clean run.)')
        elif shared:
            print('')
            print('   UNITS THAT STOPPED ON THE SAME DAY:')
            print('')
            for day in sorted(shared,
                              key=lambda d: (-len(shared[d]), d)):
                print('      %s   %d units' % (day, len(shared[day])))
                for imei in sorted(shared[day]):
                    print('                      %s' % imei)
            clustered = sum(len(v) for v in shared.values())
            print('')
            print('   %d of %d silent units share a stop date with at least'
                  % (clustered, len(silent)))
            print('   one other. That is not how devices fail individually --')
            print('   a flat battery or a cut wire does not pick the same')
            print('   calendar day as another vehicle. Each shared date is a')
            print('   candidate EVENT: a SIM or APN change, a data bundle')
            print('   lapsing, a firmware push, an ingestion or server change.')
            print('   Ask what happened on the biggest one first -- if one')
            print('   event stopped them, one fix may restore them all.')
        elif by_day:
            print('')
            print('   No two silent units share a stop date, across %d units.'
                  % len(silent))
            print('   That pattern fits devices failing individually, so')
            print('   expect per-vehicle causes rather than one event.')

        if by_day and not failures:
            print('')
            print('   Full stop-date spread (oldest first):')
            for day in sorted(by_day,
                              key=lambda d: datetime.strptime(d, '%d-%m-%Y')
                              if d and d[0].isdigit() else datetime.min):
                print('      %s  %s' % (day, '#' * len(by_day[day])))

        if args.csv:
            fields = ['imei', 'billing', 'day', 'verdict', 'basis', 'fixes',
                      'travelled_km', 'speed_claims_km', 'ratio',
                      'median_gap_s', 'coverage', 'note']
            with open(args.csv, 'w', newline='', encoding='utf-8') as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            print('')
            print('   CSV written: %s' % args.csv)

        return 0

    # ------------------------------------------------- 2. the full speed audit
    for index, (imei, billing) in enumerate(units, 1):
        line = {'imei': imei, 'billing': billing, 'day': '', 'verdict': '',
                'basis': '', 'fixes': 0, 'travelled_km': '',
                'speed_claims_km': '', 'ratio': '', 'median_gap_s': '',
                'coverage': '', 'note': ''}
        try:
            day = newest_day_with_fixes(session, imei, args.days_back,
                                        args.day)
        except location_store.PositionsUnavailable as error:
            line['verdict'] = 'read failed'
            line['note'] = str(error)[:60]
            rows.append(line)
            print('   %3d/%d  %-17s read failed' % (index, len(units), imei))
            continue

        if not day:
            line['verdict'] = 'no fixes'
            if args.trace_silent > 0:
                seen, reached = last_seen(session, imei, args.trace_silent)
                if seen:
                    line['verdict'] = 'SILENT'
                    line['note'] = 'last fix %s' % seen
                    print('   %3d/%d  %-17s SILENT        last fix %s'
                          % (index, len(units), imei, seen))
                else:
                    # NOT 'never seen'. This only establishes that no fix was
                    # found within the lookback. The store begins 05-08-2025,
                    # so only a lookback reaching that far can justify 'never'
                    # — and an earlier version of this script labelled a
                    # 365-day miss as NEVER SEEN, which was wrong for any unit
                    # last seen in Aug or Sep 2025.
                    covers_store = args.trace_silent >= full_reach_days()
                    line['verdict'] = ('NEVER SEEN' if covers_store
                                       else 'NO FIX IN %dd' % args.trace_silent)
                    line['note'] = ('no fix in the store at all'
                                    if covers_store
                                    else 'no fix in %d days; store begins %s, '
                                         'so this does NOT mean never'
                                         % (args.trace_silent,
                                            STORE_BEGINS.strftime('%d-%m-%Y')))
                    print('   %3d/%d  %-17s %-13s %s'
                          % (index, len(units), imei, line['verdict'],
                             line['note']))
            else:
                print('   %3d/%d  %-17s no fixes in the window'
                      % (index, len(units), imei))
            rows.append(line)
            continue

        line['day'] = day

        try:
            day_fixes, _t = location_store.fixes(
                session, imei, day, day,
                limit=None, dedupe_coordinates=False, newest_first=False)
        except location_store.PositionsUnavailable as error:
            line['verdict'] = 'read failed'
            line['note'] = str(error)[:60]
            rows.append(line)
            print('   %3d/%d  %-17s read failed on %s'
                  % (index, len(units), imei, day))
            continue

        plausible, detail = stops.speed_is_plausible(day_fixes)
        basis = str(detail.get('basis', ''))

        line['fixes'] = len(day_fixes)
        line['basis'] = basis
        line['travelled_km'] = detail.get('travelled_km', '')
        line['speed_claims_km'] = detail.get('integrated_km', '')
        line['median_gap_s'] = detail.get('median_gap_seconds', '')
        line['coverage'] = detail.get('speed_coverage', '')

        integrated = detail.get('integrated_km') or 0
        travelled = detail.get('travelled_km') or 0
        if integrated > 0:
            line['ratio'] = round(travelled / integrated, 1)

        if basis == 'integrated':
            line['verdict'] = 'ok' if plausible else 'FLAGGED'
        elif basis == 'no distance to explain':
            line['verdict'] = 'stationary'
        elif basis == 'no speed data':
            # Not "too few fixes": the unit reported fixes and no usable
            # speed on any of them. Every speed-derived figure for it is
            # empty rather than wrong, which is its own problem.
            line['verdict'] = 'NO SPEED DATA'
        elif basis == 'none':
            line['verdict'] = 'too few fixes'
        else:
            # max_speed bound only — passing it is not evidence of health
            line['verdict'] = 'FLAGGED' if not plausible else 'INCONCLUSIVE'
            line['note'] = 'fixes too sparse to integrate'

        rows.append(line)
        print('   %3d/%d  %-17s %-13s %-11s %6s fixes  '
              'moved %-9s speed claims %-9s %s'
              % (index, len(units), imei, line['verdict'],
                 basis.split(' ')[0], line['fixes'],
                 line['travelled_km'], line['speed_claims_km'],
                 ('x%s' % line['ratio']) if line['ratio'] else ''))

    took = time.time() - t_start

    # ---------------------------------------------------------------- report
    def of(verdict):
        return [r for r in rows if r['verdict'] == verdict]

    flagged = of('FLAGGED')
    good = of('ok')
    inconclusive = of('INCONCLUSIVE')
    stationary = of('stationary')
    nofix = of('no fixes')
    failed = of('read failed')
    toofew = of('too few fixes')
    nospeed = of('NO SPEED DATA')
    silent = of('SILENT')
    never = of('NEVER SEEN')
    unreached = [r for r in rows if str(r['verdict']).startswith('NO FIX IN')]

    print('')
    print('=' * 74)
    print('   %d units audited in %.0fs' % (len(rows), took))
    print('=' * 74)
    print('   FLAGGED  speed field cannot explain the movement   %4d'
          % len(flagged))
    print('   ok       integral agrees with the distance         %4d' % len(good))
    print('   ------- the two above are the only real verdicts -------')
    print('   INCONCLUSIVE  too sparse to integrate; NOT a pass  %4d'
          % len(inconclusive))
    print('   stationary    no distance to explain               %4d'
          % len(stationary))
    print('   NO SPEED DATA  fixes present, no usable speed       %4d'
          % len(nospeed))
    print('   too few fixes                                      %4d' % len(toofew))
    print('   no fixes in the window                             %4d' % len(nofix))
    print('   SILENT       was transmitting, has stopped          %4d' % len(silent))
    print('   NEVER SEEN   no fix anywhere in the store          %4d' % len(never))
    print('   NO FIX IN Nd  looked back N days and found none     %4d'
          % len(unreached))
    print('   read failed                                        %4d' % len(failed))

    decided = len(flagged) + len(good)
    if decided:
        print('')
        print('   Of the %d units the integral could actually judge, %d are'
              % (decided, len(flagged)))
        print('   FLAGGED — %.0f%%.' % (100.0 * len(flagged) / decided))
        print('   That percentage is over the DECIDED units only. It is not a')
        print('   fleet-wide rate, because %d more could not be judged.'
              % (len(inconclusive) + len(nofix) + len(toofew) + len(failed)
                 + len(nospeed) + len(silent) + len(never)
                 + len(unreached)))

    if flagged:
        print('')
        print('   FLAGGED units, worst first:')
        for r in sorted(flagged, key=lambda r: -(r['ratio'] or 0)):
            print('      %-17s %s  moved %s km, speed claims %s km%s'
                  % (r['imei'], r['day'], r['travelled_km'],
                     r['speed_claims_km'],
                     ('  (%sx out)' % r['ratio']) if r['ratio'] else ''))
        print('')
        print('   For these units, every speed-derived figure is wrong:')
        print('     - stops.py labels them speed_trustworthy=false already')
        print('     - trips/excel and trips/pdf publish a "Moving Speed')
        print('       ( KM/H )" column straight from this field (B3)')
        print('     - any over-speed alert or driver score built on it')
        print('     - anything Waswa says about how fast a vehicle went')

    if silent:
        print('')
        print('   SILENT — billed as running, transmitting nothing (%d):'
              % len(silent))
        for r in sorted(silent, key=lambda r: str(r['note'])):
            print('      %-17s %s' % (r['imei'], r['note']))
        print('')
        print('   These are billed as running and are not reporting. That is')
        print('   an operations and billing question, not a speed one, and it')
        print('   is a bigger finding than the one this script set out to')
        print('   measure.')

    if unreached:
        print('')
        print('   NO FIX IN %dd (%d) — these are UNRESOLVED, not absent:'
              % (args.trace_silent, len(unreached)))
        for r in unreached[:25]:
            print('      %-17s' % r['imei'])
        print('')
        print('   The store begins %s, which is %d days back. Re-run with'
              % (STORE_BEGINS.strftime('%d-%m-%Y'), full_reach_days()))
        print('   --trace-silent %d to settle whether these units have ever'
              % full_reach_days())
        print('   reported, or were only ever rows in the Postgres registry.')

    if never:
        print('')
        print('   NEVER SEEN — in the Postgres registry, no fix anywhere in '
              'the store (%d):' % len(never))
        for r in never:
            print('      %-17s %s' % (r['imei'], r['note']))
        print('')
        print('   Either these units have never transmitted, or the registry')
        print('   and the telemetry store disagree about which units exist.')
        print('   Both have been seen in this codebase: a Cassandra table')
        print('   named dll_device_basic_data holds different rows from the')
        print('   Postgres one.')

    if nospeed:
        print('')
        print('   Units reporting NO usable speed at all (%d):' % len(nospeed))
        for r in nospeed[:20]:
            print('      %-17s %s  %s fixes, moved %s km'
                  % (r['imei'], r['day'], r['fixes'], r['travelled_km']))
        print('   For these, stop detection finds nothing at all: stops.py')
        print('   refuses to treat a missing speed as zero, by design, so')
        print('   these units get no stops rather than invented ones.')

    if inconclusive:
        print('')
        print('   The INCONCLUSIVE units are the open question, not the good')
        print('   news. Re-run them on a day they were actually driving, or')
        print('   with --day, before treating any of them as sound.')

    if args.csv:
        fields = ['imei', 'billing', 'day', 'verdict', 'basis', 'fixes',
                  'travelled_km', 'speed_claims_km', 'ratio', 'median_gap_s',
                  'coverage', 'note']
        with open(args.csv, 'w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        print('')
        print('   CSV written: %s' % args.csv)

    return 0


if __name__ == '__main__':
    sys.exit(main())
