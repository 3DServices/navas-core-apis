#!/usr/bin/env python3
"""
waswa_eval_report.py -- read several runs at once and say what is stable.

Why this exists
---------------
On 9 October fb-009 was asked twice, eighteen minutes apart, with nothing
changed in between. The first run checked one unit and answered "one vehicle
is online and actively reporting ... last reported 7.3 hours ago", which
contradicts itself. The second checked all five and answered correctly.

One run is therefore not a measurement. A row that passes once has not been
shown to pass; it has been sampled once. This reads every run and reports
what held across them.

What it measures
----------------
  verdict stability   per row and per check: how often pass / fail / undecided
  answer variance     whether the FIGURES the answer claims changed between
                      runs, which is a sharper signal than the prose changing.
                      Waswa rewording itself is noise; Waswa saying 7.3 hours
                      in one run and 0.1 in the next is not.
  tool variance       whether it chose different tools for the same question

Nothing here is a single score. A number that averages a flaky row with a
stable one hides the only thing worth knowing.

Read-only: reads run files, touches no database.

Usage:
    python scripts/waswa_eval_report.py
    python scripts/waswa_eval_report.py --runs tests/waswa_eval/runs/2026*.json
    python scripts/waswa_eval_report.py --min-runs 5
"""

import argparse
import glob
import io
import json
import os
import sys

sys.path.insert(0, '.')

RUNS_DIR = os.path.join('tests', 'waswa_eval', 'runs')

# Below this, nothing can honestly be called stable.
DEFAULT_MIN_RUNS = 3


def load_runs(patterns):
    paths = []
    for pattern in patterns:
        paths.extend(sorted(glob.glob(pattern)))
    runs = []
    for path in paths:
        try:
            with io.open(path, encoding='utf-8') as fh:
                doc = json.load(fh)
        except (ValueError, OSError) as error:
            print('  skipping %s -- %s' % (path, error))
            continue
        doc['_path'] = os.path.basename(path)
        runs.append(doc)
    return runs


_RUNNER = None


def runner():
    """The runner module, loaded by path so this script does not need the
    runner to be importable as a package."""
    global _RUNNER
    if _RUNNER is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'waswa_eval_run', os.path.join('scripts', 'waswa_eval_run.py'))
        _RUNNER = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_RUNNER)
    return _RUNNER


def claimed_figures(answer):
    """The numbers an answer asserts, identifiers and dates excluded. Uses
    the runner's own extractor so the two never drift apart."""
    kept, _ = runner().numbers_in(answer)
    return tuple(sorted({value for _, value in kept}))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--runs', nargs='*',
                    default=[os.path.join(RUNS_DIR, '*.json')])
    ap.add_argument('--min-runs', type=int, default=DEFAULT_MIN_RUNS)
    args = ap.parse_args()

    runs = load_runs(args.runs)
    if not runs:
        print('no run files found. Run scripts/waswa_eval_run.py first.')
        return 1

    print('=' * 88)
    print('  %d run(s)' % len(runs))
    print('=' * 88)
    for run in runs:
        note = '  CRASHED: %s' % run['crashed'] if run.get('crashed') else ''
        print('  %-26s %s  %d row(s)%s'
              % (run['_path'], run.get('started_at'), run.get('rows', 0), note))
    # Runs scored by different rules are different experiments. Comparing
    # them row by row turns a fixed harness bug into an apparent flaky
    # system, which is exactly what happened to fb-001 and fb-003.
    prints = {}
    for run in runs:
        prints.setdefault(run.get('checks_fingerprint') or 'unversioned',
                          []).append(run['_path'])
    if len(prints) > 1:
        print('  WARNING: these runs were scored by %d different versions of'
              % len(prints))
        print('  the checks. Only runs sharing a fingerprint are compared.')
        for fp, paths in prints.items():
            print('      %-14s %s' % (fp, ', '.join(paths)))
        newest_fp = runs[-1].get('checks_fingerprint') or 'unversioned'
        dropped = [r['_path'] for r in runs
                   if (r.get('checks_fingerprint') or 'unversioned') != newest_fp]
        runs = [r for r in runs
                if (r.get('checks_fingerprint') or 'unversioned') == newest_fp]
        print('  comparing the %d run(s) on %s; setting aside %d earlier '
              'run(s).' % (len(runs), newest_fp, len(dropped)))
        print('  "unversioned" means the run predates this fingerprint, not')
        print('  that its rules differed -- but unknown is not the same as')
        print('  known-identical, so they are excluded rather than assumed.')
        print('  The cost is a smaller sample; re-run to rebuild it.')
    print('')

    # ---- gather per row ----
    rows = {}
    for run in runs:
        for result in run.get('results') or []:
            if 'checks' not in result:
                continue
            entry = rows.setdefault(result['id'], {
                'question': result['question'],
                'blocked_on': result.get('blocked_on'),
                'checks': {}, 'answers': [], 'tools': [], 'seconds': [],
            })
            entry['answers'].append((run['_path'], result['answer']))
            entry.setdefault('sources', []).append(
                tuple(result.get('cited_authorities') or []))
            entry['tools'].append(tuple(result.get('tools_used') or []))
            entry['seconds'].append(result.get('seconds'))
            for check in result['checks']:
                entry['checks'].setdefault(check['check'], []).append(
                    (check['result'], check['detail'], run['_path']))

    enough = len(runs) >= args.min_runs

    # A check the newest run did not perform has been retired from the set --
    # must_call:waswa_context asserted a tool that cannot be called and was
    # replaced. Counting its old failures against Waswa would be reading a
    # fixed harness bug as a live defect.
    newest = runs[-1]
    current_checks = {c['check'] for r in (newest.get('results') or [])
                      for c in (r.get('checks') or [])}

    # ---- verdict stability ----
    print('=' * 88)
    print('  verdict stability')
    print('=' * 88)
    if not enough:
        print('  %d run(s) is below the %d needed to call anything stable.'
              % (len(runs), args.min_runs))
        print('  Everything below is reported as sampled, not settled.')
        print('')

    flaky, always_fail, always_pass, sampled_fail = [], [], [], []
    for rid in sorted(rows):
        entry = rows[rid]
        print('  %-7s %s%s' % (rid, entry['question'][:52],
                               '   [blocked_on %s]' % entry['blocked_on']
                               if entry['blocked_on'] else ''))
        for name, outcomes in sorted(entry['checks'].items()):
            if name not in current_checks:
                print('      --    %-32s retired from the set '
                      '(%d historical result(s))' % (name, len(outcomes)))
                continue
            results = [r for r, _, _ in outcomes]
            passes = results.count(True)
            fails = results.count(False)
            undec = results.count(None)
            mixed = sum(1 for n in (passes, fails, undec) if n) > 1
            label = ('MIXED' if mixed else
                     'pass' if passes else 'FAIL' if fails else '????')
            print('      %-5s %-32s %d pass / %d fail / %d undecided'
                  % (label, name, passes, fails, undec))
            if mixed:
                flaky.append((rid, name, outcomes))
                for value, detail, path in outcomes:
                    print('            %-28s %-6s %s'
                          % (path, {True: 'pass', False: 'FAIL',
                                    None: '????'}[value], detail[:44]))
            elif fails and not entry['blocked_on'] and enough:
                always_fail.append((rid, name))
            elif fails and not entry['blocked_on']:
                sampled_fail.append((rid, name, fails))
            elif passes and not mixed and enough:
                always_pass.append((rid, name))
        print('')

    # ---- answer variance ----
    print('=' * 88)
    print('  did the answer itself change?')
    print('=' * 88)
    unstable_answers = []
    for rid in sorted(rows):
        entry = rows[rid]
        if len(entry['answers']) < 2:
            continue
        sets = [set(claimed_figures(a)) for _, a in entry['answers']]
        tools = set(entry['tools'])
        texts = {' '.join(a.split()) for _, a in entry['answers']}

        # Adding a true figure is not the same as changing one. Run 1 said
        # "120 units, 231 packs"; run 2 said "120 units across the 3 packs,
        # 231 packs" -- a superset, and strictly more informative. Run 1 said
        # the fleet was last seen 7.3 hours ago and run 2 said 0.1: each
        # claims something the other denies. Only the second is a problem,
        # and calling both "FIGURES CHANGED" cries wolf.
        contradictory = any(
            (a - b) and (b - a) for a in sets for b in sets if a is not b)
        elaborated = len({frozenset(x) for x in sets}) > 1 and not contradictory

        flags = []
        if contradictory:
            flags.append('FIGURES CONTRADICT')
        elif elaborated:
            flags.append('more detail in one run')
        if len(tools) > 1:
            flags.append('tools changed')
        sources = set(entry.get('sources') or [])
        if len(sources) > 1:
            flags.append('CITED A DIFFERENT SOURCE')
        if len(texts) > 1 and not flags:
            flags.append('wording only')
        if not flags:
            continue
        print('  %-7s %s' % (rid, ', '.join(flags)))
        if contradictory or elaborated:
            if contradictory:
                unstable_answers.append(rid)
            for path, answer in entry['answers']:
                print('      %-26s %s' % (path, claimed_figures(answer)))
                print('          %s' % ' '.join(answer.split())[:96])
        if len(sources) > 1:
            for (path, _), auth in zip(entry['answers'], entry['sources']):
                print('      %-26s document authority %s'
                      % (path, list(auth) or 'none'))
        if len(tools) > 1:
            shared = set.intersection(*[set(t) for t in entry['tools']])
            for (path, _), tool_set in zip(entry['answers'], entry['tools']):
                only = [t for t in tool_set if t not in shared]
                print('      %-26s %d tool(s); unique to this run: %s'
                      % (path, len(tool_set), ', '.join(only) or 'none'))
    if not unstable_answers:
        print('  No row changed the figures it claimed.')
    print('')

    # ---- the summary that matters ----
    print('=' * 88)
    print('  what to act on')
    print('=' * 88)
    if unstable_answers:
        print('  %d row(s) gave CONTRADICTORY figures for the same question:'
              % len(unstable_answers))
        for rid in unstable_answers:
            print('      %s' % rid)
        print('  A row that answers two ways cannot be cleared by a green run.')
        print('')
    if flaky:
        print('  %d check(s) came out differently between runs:' % len(flaky))
        for rid, name, _ in flaky:
            print('      %-7s %s' % (rid, name))
        print('')
    if always_fail:
        print('  %d check(s) failed on every run -- these are real and stable:'
              % len(always_fail))
        for rid, name in always_fail:
            print('      %-7s %s' % (rid, name))
        print('')
    if sampled_fail:
        # Saying "stable" from one run is the error this whole report exists
        # to prevent, and the first version of it made exactly that claim.
        print('  %d check(s) failed, but on too few runs to call stable:'
              % len(sampled_fail))
        for rid, name, count in sampled_fail:
            print('      %-7s %-32s failed %d of %d run(s)'
                  % (rid, name, count, len(runs)))
        print('')
    unscored = set()
    for run in runs:
        for result in run.get('results') or []:
            for item in result.get('not_scored') or []:
                unscored.add((result['id'], item['check']))
    if unscored:
        print('  %d check(s) no run can score, by design:' % len(unscored))
        for rid, name in sorted(unscored):
            print('      %-7s %s  -- needs a reader' % (rid, name))
        print('')
    if not enough:
        print('  Run the set %d more time(s) before trusting any "pass" here.'
              % (args.min_runs - len(runs)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
