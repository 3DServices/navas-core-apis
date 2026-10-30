#!/usr/bin/env python3
r"""
waswa_eval_mlflow.py -- record Waswa eval runs in MLflow.

Reads the run files waswa_eval_run.py writes, so it never calls the model or
touches the database, and it can backfill every run already on disk. Each run
file becomes one MLflow run in the "waswa-eval" experiment, named after the
file, and a file already logged is skipped -- re-running is safe.

What is logged
--------------
params   transport, checks_fingerprint, prompt_version(s), model, row count
metrics  pass_rate, rows_passed/failed/blocked, per-check pass rate,
         mean and p95 seconds per question, undecided checks
tables   one row per question: id, verdict, http status, seconds, tools,
         failing checks, answer
artifact the run file itself

Compare runs only when checks_fingerprint matches: a different fingerprint
means the scoring rules changed, not necessarily the assistant.

Usage:
    # in another terminal; 5050 because the Flask app takes Flask's 5000
    .mlflow/venv/Scripts/mlflow server --host 127.0.0.1 --port 5050 \
        --backend-store-uri sqlite:///.mlflow/mlflow.db \
        --artifacts-destination .mlflow/artifacts
    python scripts/waswa_eval_mlflow.py                       # every run
    python scripts/waswa_eval_mlflow.py tests/waswa_eval/runs/20261010-161039.json

The tracking server is MLFLOW_TRACKING_URI, defaulting to the local one above.
"""

import argparse
import datetime
import glob
import io
import json
import os
import sys

sys.path.insert(0, '.')

RUNS_DIR = os.path.join('tests', 'waswa_eval', 'runs')
EXPERIMENT = 'waswa-eval'
DEFAULT_URI = 'http://127.0.0.1:5050'


def _percentile(values, pct):
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round(pct / 100.0 * (len(ordered) - 1))))
    return ordered[index]


def summarise(run):
    """(params, metrics, table) for one run file."""
    results = run.get('results') or []
    scored = [r for r in results if 'checks' in r]
    passed = [r for r in scored if r.get('passed')]
    blocked = [r for r in scored if r.get('blocked_on') and not r.get('passed')]
    seconds = [r['seconds'] for r in scored if r.get('seconds') is not None]

    prompt_versions = sorted({str(r.get('prompt_version')) for r in scored
                              if r.get('prompt_version')})
    agent_versions = sorted({str(r.get('agent_version')) for r in scored
                             if r.get('agent_version')})
    params = {
        'agent_version': ','.join(agent_versions) or 'unrecorded',
        'transport': run.get('transport'),
        'checks_fingerprint': run.get('checks_fingerprint') or 'unversioned',
        'prompt_version': ','.join(prompt_versions) or 'none',
        'rows': run.get('rows'),
        'crashed': bool(run.get('crashed')),
    }
    try:
        from config import OPENROUTER_MODEL
        # The model is not in the run file. Only stamp it on a run being
        # logged as it happens; for a backfill it would be today's model.
        params['model_at_log_time'] = OPENROUTER_MODEL
    except Exception:                                   # noqa: BLE001
        pass

    metrics = {
        'rows_scored': len(scored),
        'rows_passed': len(passed),
        'rows_failed': len(scored) - len(passed),
        'rows_blocked': len(blocked),
        'pass_rate': (len(passed) / float(len(scored))) if scored else 0.0,
        'undecided_checks': sum(r.get('undecided') or 0 for r in scored),
        'http_errors': sum(1 for r in scored
                           if (r.get('http_status') or 0) >= 400),
    }
    if seconds:
        metrics['seconds_mean'] = sum(seconds) / len(seconds)
        metrics['seconds_p95'] = _percentile(seconds, 95)

    # Per-check pass rate over the rows that were scored on that check.
    # None ("cannot decide") is excluded from both sides.
    tally = {}
    for r in scored:
        for c in r.get('checks') or []:
            if c.get('result') is None:
                continue
            name = c['check'].replace(':', '.')
            ok, total = tally.get(name, (0, 0))
            tally[name] = (ok + (1 if c['result'] else 0), total + 1)
    for name, (ok, total) in tally.items():
        metrics['check.%s' % name] = ok / float(total)

    table = {'id': [], 'verdict': [], 'http_status': [], 'seconds': [],
             'tools': [], 'failed_checks': [], 'answer': []}
    for r in scored:
        failing = [c['check'] for c in r.get('checks') or []
                   if c.get('result') is False]
        verdict = 'PASS' if r.get('passed') else (
            'BLOCKED' if r.get('blocked_on') else 'FAIL')
        table['id'].append(r.get('id'))
        table['verdict'].append(verdict)
        table['http_status'].append(r.get('http_status'))
        table['seconds'].append(r.get('seconds'))
        table['tools'].append(', '.join(r.get('tools_used') or []))
        table['failed_checks'].append(', '.join(failing))
        table['answer'].append(r.get('answer') or '')
    return params, metrics, table


def already_logged(client, experiment_id, run_name):
    hits = client.search_runs(
        [experiment_id],
        filter_string="tags.run_file = '%s'" % run_name,
        max_results=1)
    return bool(hits)


def log_run(path, live=False):
    """Log one run file. Returns the MLflow run id, or None if skipped."""
    import mlflow
    from mlflow.tracking import MlflowClient

    run_name = os.path.basename(path)
    with io.open(path, encoding='utf-8') as fh:
        run = json.load(fh)

    experiment = mlflow.set_experiment(EXPERIMENT)
    if already_logged(MlflowClient(), experiment.experiment_id, run_name):
        print('  %-22s already logged, skipped' % run_name)
        return None

    params, metrics, table = summarise(run)
    if not live:
        params.pop('model_at_log_time', None)

    started = run.get('started_at')
    start_ms = None
    if started:
        start_ms = int(datetime.datetime.fromisoformat(started)
                       .timestamp() * 1000)

    with mlflow.start_run(run_name=run_name.rsplit('.', 1)[0]) as active:
        mlflow.set_tags({'run_file': run_name,
                         'started_at': started or '',
                         'logged': 'live' if live else 'backfill'})
        mlflow.log_params(params)
        mlflow.log_metrics(metrics, timestamp=start_ms)
        if table['id']:
            mlflow.log_table(table, artifact_file='results.json')
        mlflow.log_artifact(path, artifact_path='run_file')
        run_id = active.info.run_id

    print('  %-22s %d/%d passed  -> %s'
          % (run_name, metrics['rows_passed'], metrics['rows_scored'], run_id))
    return run_id


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('run_files', nargs='*',
                    help='run files to log; default is every file in %s'
                         % RUNS_DIR)
    args = ap.parse_args()

    import mlflow
    mlflow.set_tracking_uri(os.environ.get('MLFLOW_TRACKING_URI', DEFAULT_URI))

    paths = args.run_files or sorted(
        glob.glob(os.path.join(RUNS_DIR, '[0-9]*-[0-9]*.json')))
    if not paths:
        print('no run files found')
        return 1
    print('logging %d run file(s) to %s, experiment "%s"'
          % (len(paths), mlflow.get_tracking_uri(), EXPERIMENT))
    for path in paths:
        log_run(path)
    return 0


if __name__ == '__main__':
    sys.exit(main())
