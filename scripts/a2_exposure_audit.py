#!/usr/bin/env python3
"""
a2_exposure_audit.py -- which live secrets are recoverable from git history?

A2 has been described from memory three times in this project and the list has
drifted.  This derives it from the repository instead of restating it.

Method: read every secret value currently in .env, then stream EVERY blob in
the repository's full object set (all refs, all commits, including unreachable
objects) and report which of those exact values appear, in which commit and
file.  65 commits / 7 MB, so the scan is exhaustive rather than sampled.

A secret that appears in history is recoverable by anyone who has ever cloned
or been given read access, and rotating it is urgent.  A secret that does NOT
appear has only ever lived in the gitignored .env, and rotating it is hygiene
rather than an emergency.  The distinction decides the order of work, which is
why this is measured instead of assumed.

OUTPUT CONTAINS NO SECRET VALUES.  Each is identified by its .env key name,
character length and a 10-character SHA-256 prefix.  The prefix is enough to
tell whether two places hold the same value without disclosing either.

Read-only: reads .env and git objects, writes nothing, changes no history.

Usage:
    python scripts/a2_exposure_audit.py
"""

import hashlib
import io
import os
import subprocess
import sys


def fingerprint(value):
    return hashlib.sha256(value.encode('utf-8', 'replace')).hexdigest()[:10]


def load_env(path='.env'):
    """Secret-looking values from .env, as {key: value}."""
    if not os.path.exists(path):
        return {}

    skip_keys = ('BASE_URL', 'CORS_ORIGINS', 'OPENROUTER_MODEL',
                 'OPENROUTER_SITE_NAME', 'OPENROUTER_SITE_URL',
                 'JWT_ACCESS_EXPIRY_MINUTES', 'JWT_REFRESH_EXPIRY_DAYS',
                 'CASSANDRA_KEYSPACE', 'CASSANDRA_PORT', 'CASSANDRA_USERNAME',
                 'CASSANDRA_LOCAL_DC', 'CASSANDRA_CONTACT_POINTS')

    found = {}
    for line in io.open(path, encoding='utf-8', errors='replace'):
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if len(value) < 8 or key in skip_keys:
            continue
        found[key] = value
    return found


def extract_password(dsn):
    """The password half of a URI DSN, if there is one."""
    import re
    match = re.search(r'://[^\s:/@]*:([^\s@]+)@', dsn)
    return match.group(1) if match else None


def git(*args):
    return subprocess.run(('git',) + args, capture_output=True, text=True,
                          errors='replace').stdout


def main():
    secrets = load_env()

    if not secrets:
        print('no .env found -- nothing to check')
        return 1

    # the DSN's password is the thing that actually grants access, so test it
    # separately from the whole connection string
    for key in list(secrets):
        if 'DATABASE_URL' in key or key.endswith('_URL') or key == 'DB_LINK':
            password = extract_password(secrets[key])
            if password and len(password) >= 8:
                secrets[key + ' (password only)'] = password

    print('=' * 74)
    print('LIVE SECRETS IN .env')
    print('=' * 74)
    for key in sorted(secrets):
        print('   %-36s %4d chars  sha256:%s'
              % (key, len(secrets[key]), fingerprint(secrets[key])))

    # ---- scan history
    #
    # The first version of this spawned two `git cat-file` processes per
    # object and timed out: thousands of process spawns, not a slow scan.
    # `git log --all -p` emits every added and removed line across all
    # reachable commits in ONE process, which covers every committed version
    # of every file -- and `git cat-file --batch-all-objects --batch` adds
    # objects no commit reaches, also in one process.  Both are used.
    print('')
    print('=' * 74)
    print('SCANNING HISTORY')
    print('=' * 74)

    diffs = git('log', '--all', '-p', '--format=commit %H')
    print('   %d bytes of diff across all reachable commits' % len(diffs))

    allobjects = subprocess.run(
        ('git', 'cat-file', '--batch-all-objects', '--batch',
         '--buffer'),
        capture_output=True, text=True, errors='replace').stdout
    print('   %d bytes from every object in the database '
          '(including unreachable)' % len(allobjects))

    hits = {}

    for key, value in secrets.items():
        where = []
        if value in diffs:
            where.append('reachable commit history')
        if value in allobjects:
            where.append('object database')
        if where:
            hits[key] = where

    # locate the commit for each hit, by walking the diff for the value
    located = {}
    for key in hits:
        value = secrets[key]
        current_commit = None
        for line in diffs.split('\n'):
            if line.startswith('commit '):
                current_commit = line.split()[1][:9]
            elif value in line:
                located.setdefault(key, []).append(current_commit)

    # ---- which commits introduced them
    print('')
    print('=' * 74)
    print('RESULT')
    print('=' * 74)

    exposed = sorted(hits)
    clean = sorted(k for k in secrets if k not in hits)

    if exposed:
        print('')
        print('   RECOVERABLE FROM HISTORY -- rotate these first:')
        for key in exposed:
            print('')
            print('   %s  (sha256:%s)' % (key, fingerprint(secrets[key])))
            print('      found in: %s' % ', '.join(hits[key]))
            for commit in dict.fromkeys(located.get(key, [])):
                if commit:
                    line = git('log', '-1', '--format=%h %ad %s',
                               '--date=short', commit).strip()
                    print('      %s' % line[:92])
    else:
        print('')
        print('   Nothing in .env appears anywhere in git history.')

    if clean:
        print('')
        print('   NOT in history -- rotate as hygiene, not as an emergency:')
        for key in clean:
            print('      %-36s sha256:%s' % (key, fingerprint(secrets[key])))

    print('')
    print('=' * 74)
    print('WHAT THIS DOES AND DOES NOT PROVE')
    print('=' * 74)
    print('   Proves: these exact byte sequences are / are not present in')
    print('   objects reachable from this clone\'s refs.')
    print('')
    print('   Does NOT prove safety for a "clean" secret.  It could still')
    print('   have been pasted into a chat, a ticket, a CI log, a screenshot')
    print('   or a teammate\'s shell history, none of which this can see.')
    print('   And an EXPOSED secret stays exposed in every existing clone and')
    print('   fork even after the history is rewritten -- rewriting does not')
    print('   un-disclose it.  Rotation is the only thing that does.')

    return 0


if __name__ == '__main__':
    sys.exit(main())
