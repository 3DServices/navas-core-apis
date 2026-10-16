"""
waswa_app_guide.py -- keep an app's how-to guide in Waswa's corpus, in step
with the app.

WHY
Asked "how do I create a geofence?" from the OLIWA app, Waswa could only say
it had no instructions: the corpus held the CMS manual and user stories, and
nothing describing the app people were holding. The guide that fills that gap
is written from the app's source (oliwa-mobile/docs/user-guide) and has to
change whenever the app does, so it is published by a sync, not by hand.

HOW
A sync sends the whole guide for one app -- every article, as Markdown, with
the app commit it was checked against. Each article becomes an ordinary
document, through the same pipeline as an upload from the AI Console
(waswa_documents.upload): converted, currency withheld, chunked, versioned.
dll_waswa_app_guide (migration 046) remembers which document is the current
version of each (app, slug), so:

  unchanged  body hash matches the newest version    -> nothing is written
  changed    a new version replacing the current one -> the old one keeps
             answering until the new one is approved
  new        a new document
  missing    with prune=true, removed (reversibly) from the corpus

Re-running a sync with nothing changed writes nothing.

REVIEW
publish=false (the default) leaves new versions awaiting review in the AI
Console, like any upload. publish=true approves them in the same step, and is
refused up front unless the caller may approve their own uploads -- the same
rule review() applies, checked before anything is written so that a sync
never half-applies.

SCOPE
Every title starts with the app's guide prefix ("OLIWA Mobile App Guide:"),
which is what waswa_v2.document_scope reads: these chunks count as the mobile
app's, and are the only ones the v2 guard will offer for a how-to asked from
the app.

Routes (registered onto assistant_bp, same gate as the console):
    GET  /assistant/console/app-guide/<app>        articles and their state
    POST /assistant/console/app-guide/<app>/sync   publish a whole guide
"""

import hashlib
import re
from datetime import date

from flask import request

from . import waswa_answers as wa
from . import waswa_documents as wd

# The apps a guide can be synced for. A new app is a line here, so an
# arbitrary name in a URL cannot create a corpus nobody reviews.
APPS = {
    'oliwa-mobile': {
        'prefix': 'OLIWA Mobile App Guide',
        'applies_to': 'the OLIWA mobile app (Android and iOS)',
    },
}

MAX_ARTICLES = 200
MAX_BODY_CHARS = 60_000
_SLUG = re.compile(r'^[a-z0-9][a-z0-9-]{1,118}[a-z0-9]$')
_COMMIT = re.compile(r'^[0-9a-f]{7,40}$')

DOCUMENT_TYPE = 'manual'
# Level 2, as the NAVAS CMS User Manual: approved and quotable. The guide is
# checked against the app itself, which is more than a specification (4) can
# claim, and less than structured product data (1).
AUTHORITY_LEVEL = 2


def _hash(body):
    """Hash of the article as written, whitespace-normalised, so a reflow or
    a trailing newline is not a new version."""
    normal = re.sub(r'\s+', ' ', body).strip()
    return hashlib.sha256(normal.encode('utf-8')).hexdigest()


# Bump when render() changes what is stored, so the next sync re-uploads
# every article even though no article text changed.
RENDER_VERSION = 2

_H2 = re.compile(r'^## +(.+?)[ 	]*$', re.M)


def render(app, title, body, commit, summary=None, asked_as=None):
    """The document as stored. The header names the app and the commit, so
    an answer built from it can be traced to a version of the app; the commit
    also makes each version's bytes distinct, which the upload's duplicate
    check needs when a later version reverts to earlier wording.

    Each section heading is prefixed with the task ("Create a geofence:
    Steps"). The chunker keeps only the section heading on a chunk, and the
    search weights headings highest, so without the task every article's
    steps were headed just "Steps" -- and "create a new geofence" ranked the
    Edit article, whose body happens to contain that phrase, above the
    Create article. The summary and the phrasings people use ("add a
    geofence") are included for the same reason: they are how people ask.
    """
    spec = APPS[app]
    parts = [f"# {spec['prefix']}: {title}",
             f"Applies to {spec['applies_to']}. Checked against app version "
             f"{commit[:12]} on {date.today().isoformat()}."]
    if summary:
        parts.append(summary.strip())
    if asked_as:
        parts.append('Also asked as: ' + '; '.join(asked_as) + '.')
    parts.append(_H2.sub(lambda m: f'## {title}: {m.group(1)}', body.strip()))
    return '\n\n'.join(parts) + '\n'


def _validate(app, payload):
    if app not in APPS:
        raise wa.RuleError(f"No guide is configured for app '{app}'. "
                           f"Known apps: {', '.join(sorted(APPS))}.", 404)
    commit = str(payload.get('commit') or '').strip().lower()
    if not _COMMIT.match(commit):
        raise wa.RuleError('commit must be the app git commit (7-40 hex '
                           'characters) the guide was checked against.')
    articles = payload.get('articles')
    if not isinstance(articles, list) or not articles:
        raise wa.RuleError('articles must be a non-empty list.')
    if len(articles) > MAX_ARTICLES:
        raise wa.RuleError(f'At most {MAX_ARTICLES} articles per sync.')
    seen, clean = set(), []
    for index, item in enumerate(articles):
        if not isinstance(item, dict):
            raise wa.RuleError(f'articles[{index}] must be an object.')
        slug = str(item.get('slug') or '').strip()
        title = re.sub(r'\s+', ' ', str(item.get('title') or '')).strip()
        body = str(item.get('body') or '')
        if not _SLUG.match(slug):
            raise wa.RuleError(f"articles[{index}].slug '{slug}' must be "
                               f"lowercase letters, digits and hyphens.")
        if slug in seen:
            raise wa.RuleError(f"slug '{slug}' appears twice.")
        if not title or len(title) > 200:
            raise wa.RuleError(f"'{slug}': title is required (200 chars max).")
        if not body.strip() or len(body) > MAX_BODY_CHARS:
            raise wa.RuleError(f"'{slug}': body is required "
                               f"({MAX_BODY_CHARS} chars max).")
        summary = re.sub(r'\s+', ' ', str(item.get('summary') or '')).strip()
        if len(summary) > 400:
            raise wa.RuleError(f"'{slug}': summary is longer than 400 chars.")
        asked_as = item.get('asked_as') or []
        if (not isinstance(asked_as, list) or len(asked_as) > 12
                or any(not isinstance(a, str) or not a.strip() or len(a) > 100
                       for a in asked_as)):
            raise wa.RuleError(f"'{slug}': asked_as must be a list of up to "
                               f"12 short phrases.")
        asked_as = [re.sub(r'\s+', ' ', a).strip() for a in asked_as]
        seen.add(slug)
        clean.append({'slug': slug, 'title': title, 'body': body,
                      'summary': summary, 'asked_as': asked_as,
                      'hash': _hash(f'v{RENDER_VERSION}\n{title}\n{summary}\n'
                                    f'{"; ".join(asked_as)}\n{body}')})
    return commit, clean


def _current(cur, app):
    cur.execute("SELECT slug, source_uid, content_hash FROM dll_waswa_app_guide "
                "WHERE app = %s FOR UPDATE", (app,))
    return {r[0]: {'source_uid': r[1], 'hash': r[2]} for r in cur.fetchall()}


def _live_base(cur, source_uid):
    """The document a new version should replace: [source_uid] if it is
    live and not already replaced, else None (upload as a new document)."""
    if not source_uid:
        return None
    try:
        doc = wd.get_source(cur, source_uid)
    except wa.RuleError:
        return None
    if doc['active'] and not doc['superseded_by'] \
            and doc['review_status'] == 'approved':
        return source_uid
    return None


def plan(cur, app, articles):
    """What a sync would do, per article, without writing anything."""
    mapped = _current(cur, app)
    steps = []
    for article in articles:
        row = mapped.get(article['slug'])
        if row is None:
            steps.append({'slug': article['slug'], 'action': 'create'})
            continue
        doc = None
        try:
            doc = wd.get_source(cur, row['source_uid'])
        except wa.RuleError:
            pass
        usable = doc and doc['active'] and doc['review_status'] != 'rejected'
        if row['hash'] == article['hash'] and usable:
            steps.append({'slug': article['slug'], 'action': 'unchanged',
                          'review_status': doc['review_status']})
        else:
            steps.append({'slug': article['slug'], 'action': 'update'})
    wanted = {a['slug'] for a in articles}
    for slug in sorted(set(mapped) - wanted):
        steps.append({'slug': slug, 'action': 'missing'})
    return steps


def sync(cur, who, app, payload):
    commit, articles = _validate(app, payload)
    publish = bool(payload.get('publish'))
    prune = bool(payload.get('prune'))
    dry_run = bool(payload.get('dry_run'))

    if publish and not (wa.can(who, wa.PERM_APPROVE) and who.get('is_admin')):
        # review() lets only an administrator approve their own upload. Said
        # here, before anything is written, rather than after half a guide.
        raise wa.RuleError('publish=true needs an administrator with the '
                           'waswa.approve permission: a sync approves its own '
                           'uploads. Sync without publish to leave the new '
                           'versions for a reviewer.', 403)

    steps = plan(cur, app, articles)
    if dry_run:
        return {'app': app, 'commit': commit, 'dry_run': True,
                'steps': steps, 'counts': _counts(steps)}

    spec = APPS[app]
    by_slug = {a['slug']: a for a in articles}
    mapped = _current(cur, app)
    for step in steps:
        slug = step['slug']
        if step['action'] in ('create', 'update'):
            article = by_slug[slug]
            base = None
            row = mapped.get(slug)
            if row:
                base = _superseded_pending(cur, who, row['source_uid'])
            markdown = render(app, article['title'], article['body'], commit,
                              article['summary'], article['asked_as'])
            doc = wd.upload(cur, who, f'{slug}.md', markdown.encode('utf-8'), {
                'title': f"{spec['prefix']}: {article['title']}",
                'document_type': DOCUMENT_TYPE,
                'authority_level': AUTHORITY_LEVEL,
                'audience': 'everyone',
                'version_label': commit[:12],
                'replaces_source_uid': base,
                'notes': f'app guide {app}/{slug}',
                'publish': 'true' if publish else '',
                'publish_note': f'App guide sync at {commit[:12]}.',
            })
            cur.execute(
                "INSERT INTO dll_waswa_app_guide "
                "(app, slug, title, source_uid, content_hash, app_commit, "
                " synced_by, synced_at) VALUES (%s,%s,%s,%s,%s,%s,%s,NOW()) "
                "ON CONFLICT (app, slug) DO UPDATE SET title = EXCLUDED.title, "
                "source_uid = EXCLUDED.source_uid, "
                "content_hash = EXCLUDED.content_hash, "
                "app_commit = EXCLUDED.app_commit, "
                "synced_by = EXCLUDED.synced_by, synced_at = NOW()",
                (app, slug, article['title'], doc['source_uid'], article['hash'],
                 commit, who['account_uid']))
            step.update(source_uid=doc['source_uid'],
                        review_status=doc['review_status'],
                        replaces=base, passages=doc.get('chunk_count'))
        elif step['action'] == 'unchanged':
            cur.execute("UPDATE dll_waswa_app_guide SET app_commit = %s, "
                        "synced_at = NOW() WHERE app = %s AND slug = %s",
                        (commit, app, slug))
        elif step['action'] == 'missing' and prune:
            source_uid = mapped[slug]['source_uid']
            wd.remove(cur, who, source_uid,
                      f'No longer in the {app} guide as of {commit[:12]}.')
            cur.execute("DELETE FROM dll_waswa_app_guide "
                        "WHERE app = %s AND slug = %s", (app, slug))
            step['action'] = 'removed'
            step['source_uid'] = source_uid

    wa.log(cur, who, 'knowledge_change', 'app_guide_synced',
           f"{app} guide synced at {commit[:12]}: " + ', '.join(
               f'{n} {k}' for k, n in sorted(_counts(steps).items())),
           {'app': app, 'commit': commit, 'publish': publish, 'prune': prune})
    return {'app': app, 'commit': commit, 'dry_run': False,
            'published': publish, 'steps': steps, 'counts': _counts(steps)}


def _superseded_pending(cur, who, source_uid):
    """The live document a new version should replace.

    If the newest version is still awaiting review, it is rejected first --
    the app has moved on and it no longer describes it -- and the new version
    replaces whatever is live. upload() refuses a second pending version of
    one document, so without this a sync could never get past an unreviewed
    one.
    """
    try:
        doc = wd.get_source(cur, source_uid)
    except wa.RuleError:
        return None
    if doc['active'] and doc['review_status'] == 'pending':
        wd.review(cur, who, source_uid, 'reject',
                  'Replaced by a newer app guide sync before it was reviewed.')
        return _live_base(cur, doc['replaces_source_uid'])
    if doc['review_status'] == 'rejected':
        return _live_base(cur, doc['replaces_source_uid'])
    return _live_base(cur, source_uid)


def _counts(steps):
    counts = {}
    for step in steps:
        counts[step['action']] = counts.get(step['action'], 0) + 1
    return counts


def listing(cur, app):
    if app not in APPS:
        raise wa.RuleError(f"No guide is configured for app '{app}'.", 404)
    cur.execute(
        "SELECT g.slug, g.title, g.source_uid, g.app_commit, g.synced_at, "
        "       s.review_status, s.active, s.superseded_by, s.chunk_count "
        "FROM dll_waswa_app_guide g "
        "JOIN dll_waswa_sources s USING (source_uid) "
        "WHERE g.app = %s ORDER BY g.slug", (app,))
    keys = ('slug', 'title', 'source_uid', 'app_commit', 'synced_at',
            'review_status', 'active', 'superseded_by', 'passages')
    items = []
    for row in cur.fetchall():
        item = dict(zip(keys, row))
        item['synced_at'] = item['synced_at'].isoformat()
        item['live'] = (item['active'] and item['review_status'] == 'approved'
                        and not item['superseded_by'])
        items.append(item)
    return {'app': app, 'articles': items, 'count': len(items),
            'live': sum(1 for i in items if i['live'])}


# ── Routes ─────────────────────────────────────────────────────────────────

def register(blueprint):
    # Imported here: waswa_console imports nothing from this module, and the
    # gate and transaction helpers are the console's own.
    from .waswa_console import _body, _gate, _read, _run

    @_gate(wa.PERM_REVIEW)
    def app_guide(app):
        return _read(lambda cur, who: listing(cur, app))

    @_gate(wa.PERM_REVIEW)
    def app_guide_sync(app):
        payload = _body()
        if request.args.get('dry_run') in ('1', 'true'):
            payload['dry_run'] = True
        return _run(
            lambda cur, who: sync(cur, who, app, payload),
            audit=lambda result: (
                'WASWA_APP_GUIDE_SYNC',
                f"{result['app']} @ {result['commit'][:12]}: {result['counts']}"
                + (' (dry run)' if result['dry_run'] else '')))

    blueprint.add_url_rule('/assistant/console/app-guide/<app>',
                           endpoint='waswa_app_guide_list',
                           view_func=app_guide, methods=['GET'])
    blueprint.add_url_rule('/assistant/console/app-guide/<app>/sync',
                           endpoint='waswa_app_guide_sync',
                           view_func=app_guide_sync, methods=['POST'])
