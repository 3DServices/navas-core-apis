"""tests/test_waswa_app_guide.py -- syncing an app guide into Waswa's corpus.

Every test runs inside one database transaction that is rolled back, under a
test app name, so nothing reaches the live corpus. The upload pipeline also
writes each document to disk (waswa_documents.upload_root()); those folders
are deleted afterwards.

What is checked:
  * a first sync creates every article; a repeat with nothing changed writes
    nothing; a changed article becomes a new version of the old one;
  * an unreviewed version is rejected when a newer sync supersedes it, so a
    sync never gets stuck behind a pending upload;
  * publish approves in the same step, the old version stops answering, and
    publish is refused up front for anyone who may not self-approve;
  * prune removes (reversibly) an article that left the guide;
  * dry_run writes nothing; bad input is refused before anything is written;
  * the stored chunks read as the mobile app's to v2's scope guard, and the
    app_guide filter returns this guide and nothing else.

Run:  python tests/test_waswa_app_guide.py   (or via pytest)
"""

import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

APP = 'test-guide-app'
COMMIT_1 = 'a1b2c3d4e5f6a7b8c9d0'
COMMIT_2 = 'b2c3d4e5f6a7b8c9d0e1'


def _setup():
    from app import app
    from endpoints import waswa_answers as wa
    from endpoints import waswa_app_guide as ag
    ag.APPS[APP] = dict(ag.APPS['oliwa-mobile'])
    admin = {'account_uid': 'test-app-guide-admin', 'role': 'admin',
             'account_type': 'system_account', 'account_root': None,
             'is_admin': True, 'permissions': [],
             '_granted': {wa.PERM_STAFF, wa.PERM_REVIEW, wa.PERM_APPROVE}}
    reviewer = dict(admin, account_uid='test-app-guide-reviewer',
                    is_admin=False, _granted={wa.PERM_REVIEW})
    return app, ag, wa, admin, reviewer


def _articles(**bodies):
    base = {
        'create-thing': ('Create a thing',
                         '## Steps\n\n1. Open **Things**.\n2. Tap **New**.\n'
                         '3. Fill in the name and tap **Create**.\n\n'
                         'You will see "Thing created."'),
        'delete-thing': ('Delete a thing',
                         '## Steps\n\n1. Open **Things**.\n2. Tap the menu '
                         'on the card, then **Delete**.\n3. Confirm with '
                         '**Delete**.'),
    }
    base.update({k: (base[k][0], v) for k, v in bodies.items()})
    return [{'slug': slug, 'title': title, 'body': body}
            for slug, (title, body) in base.items()]


class _Tx:
    """A cursor in a transaction that is always rolled back, plus cleanup of
    the files the uploads wrote."""

    def __enter__(self):
        import psycopg2
        from config import DB_LINK
        self.app, self.ag, self.wa, self.admin, self.reviewer = _setup()
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.conn = psycopg2.connect(DB_LINK)
        self.cur = self.conn.cursor()
        return self

    def sources(self):
        self.cur.execute("SELECT source_uid FROM dll_waswa_app_guide "
                         "WHERE app = %s", (APP,))
        mapped = [r[0] for r in self.cur.fetchall()]
        self.cur.execute("SELECT source_uid, review_status, superseded_by, "
                         "active FROM dll_waswa_sources "
                         "WHERE notes LIKE %s", (f'app guide {APP}/%',))
        return mapped, {r[0]: r[1:] for r in self.cur.fetchall()}

    def __exit__(self, *exc):
        from endpoints import waswa_documents as wd
        try:
            _, docs = self.sources()
        except Exception:                               # noqa: BLE001
            docs = {}
        self.conn.rollback()
        self.conn.close()
        for source_uid in docs:
            path = os.path.join(wd.upload_root(), source_uid)
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
        self.ctx.pop()
        return False


def _sync(t, who, articles, commit=COMMIT_1, **flags):
    return t.ag.sync(t.cur, who, APP,
                     dict(flags, commit=commit, articles=articles))


def test_first_sync_creates_and_a_repeat_writes_nothing():
    with _Tx() as t:
        first = _sync(t, t.reviewer, _articles())
        assert first['counts'] == {'create': 2}, first['counts']
        assert all(s['review_status'] == 'pending' for s in first['steps'])
        mapped, docs = t.sources()
        assert len(mapped) == 2 and len(docs) == 2

        again = _sync(t, t.reviewer, _articles(), commit=COMMIT_2)
        assert again['counts'] == {'unchanged': 2}, again['counts']
        _, docs_after = t.sources()
        assert docs_after.keys() == docs.keys(), 'a repeat wrote documents'


def test_a_change_supersedes_an_unreviewed_version():
    with _Tx() as t:
        first = _sync(t, t.reviewer, _articles())
        old = next(s['source_uid'] for s in first['steps']
                   if s['slug'] == 'create-thing')
        second = _sync(t, t.reviewer, _articles(**{
            'create-thing': '## Steps\n\n1. Open **Things**.\n2. Tap **Add**.'
                            '\n3. Tap **Create**.'}), commit=COMMIT_2)
        assert second['counts'] == {'update': 1, 'unchanged': 1}, second['counts']
        _, docs = t.sources()
        assert docs[old][0] == 'rejected', docs[old]
        new = next(s['source_uid'] for s in second['steps']
                   if s['slug'] == 'create-thing')
        assert docs[new][0] == 'pending'


def test_publish_goes_live_and_replaces_the_old_version():
    with _Tx() as t:
        first = _sync(t, t.admin, _articles(), publish=True)
        assert all(s['review_status'] == 'approved' for s in first['steps'])
        old = next(s['source_uid'] for s in first['steps']
                   if s['slug'] == 'delete-thing')
        second = _sync(t, t.admin, _articles(**{
            'delete-thing': '## Steps\n\n1. Open **Things**.\n2. Swipe left.'}),
            commit=COMMIT_2, publish=True)
        new = next(s for s in second['steps'] if s['slug'] == 'delete-thing')
        assert new['action'] == 'update' and new['replaces'] == old, new
        _, docs = t.sources()
        assert docs[old][1] == new['source_uid'], 'old version still live'
        assert docs[new['source_uid']][0] == 'approved'


def test_publish_is_refused_up_front_without_self_approval():
    with _Tx() as t:
        try:
            _sync(t, t.reviewer, _articles(), publish=True)
        except t.wa.RuleError as error:
            assert error.status == 403
        else:
            raise AssertionError('a reviewer published their own upload')
        mapped, docs = t.sources()
        assert not mapped and not docs, 'something was written first'


def test_prune_removes_an_article_that_left_the_guide():
    with _Tx() as t:
        _sync(t, t.admin, _articles(), publish=True)
        only_one = [a for a in _articles() if a['slug'] == 'create-thing']
        kept = _sync(t, t.admin, only_one, commit=COMMIT_2)
        assert kept['counts'] == {'unchanged': 1, 'missing': 1}, kept['counts']
        pruned = _sync(t, t.admin, only_one, commit=COMMIT_2, prune=True)
        removed = [s for s in pruned['steps'] if s['action'] == 'removed']
        assert len(removed) == 1 and removed[0]['slug'] == 'delete-thing'
        _, docs = t.sources()
        assert docs[removed[0]['source_uid']][2] is False, 'still active'


def test_dry_run_writes_nothing():
    with _Tx() as t:
        plan = _sync(t, t.admin, _articles(), dry_run=True, publish=True)
        assert plan['dry_run'] and plan['counts'] == {'create': 2}
        mapped, docs = t.sources()
        assert not mapped and not docs


def test_bad_input_is_refused():
    with _Tx() as t:
        cases = [
            ([{'slug': 'Bad Slug', 'title': 'x', 'body': 'y'}], COMMIT_1),
            (_articles() + _articles()[:1], COMMIT_1),
            (_articles(), 'not-a-commit'),
            ([], COMMIT_1),
            ([{'slug': 'ok-slug', 'title': '', 'body': 'y'}], COMMIT_1),
        ]
        for articles, commit in cases:
            try:
                _sync(t, t.admin, articles, commit=commit)
            except t.wa.RuleError as error:
                assert error.status == 400, error.status
            else:
                raise AssertionError(f'accepted {articles!r} @ {commit}')
        try:
            t.ag.sync(t.cur, t.admin, 'no-such-app',
                      {'commit': COMMIT_1, 'articles': _articles()})
        except t.wa.RuleError as error:
            assert error.status == 404
        else:
            raise AssertionError('accepted an unknown app')


def test_chunks_are_mobile_scoped_and_the_filter_finds_only_the_guide():
    from endpoints import waswa_knowledge as wk
    from endpoints import waswa_v2
    with _Tx() as t:
        _sync(t, t.admin, _articles(), publish=True)
        rows, how = wk._search(t.cur, 'create thing', {'app_guide': APP}, 8,
                               False, 'everyone')
        assert rows, 'the guide was not found through its own filter'
        found = [wk._row(r) for r in rows]
        _, docs = t.sources()
        assert {f['chunk_uid'].rsplit('-', 1)[0] for f in found} <= set(docs), \
            'the app_guide filter returned a document outside the guide'
        for item in found:
            scope = waswa_v2.document_scope(item)
            assert scope == 'mobile', (item.get('source'), scope)


def test_whole_articles_rank_by_what_names_the_task():
    """Article-level search (app_guide_search). The Edit article's body says
    "create a new one", which used to outrank the Create article on chunk
    proximity; the title and asked_as phrasings must decide instead."""
    from endpoints import waswa_knowledge as wk
    articles = _articles()
    articles.append({
        'slug': 'edit-thing', 'title': 'Edit a thing',
        'asked_as': ['rename a thing'],
        'body': '## Steps\n\n1. Open **Things**.\n2. Tap **Edit**.\n\n'
                'To change its shape, create a new thing and delete this one.'})
    articles[0]['asked_as'] = ['add a thing', 'make a new thing']
    with _Tx() as t:
        _sync(t, t.admin, articles, publish=True)

        def top(query):
            rows = wk._article_search(t.cur, query, APP, 3, 'everyone')
            return rows[0][1].split(': ', 1)[-1] if rows else None

        assert top('create a new thing') == 'Create a thing', top('create a new thing')
        assert top('how do I add a thing') == 'Create a thing'
        assert top('rename my thing') == 'Edit a thing'
        assert top('delete a thing') == 'Delete a thing'
        # Off-topic, or one shared word only: nothing, not a wrong article.
        assert top('recipe for chapati') is None
        assert top('fix my thing engine') is None
        # A stop word must not block a match ("now" can never match).
        assert top('delete a thing now') == 'Delete a thing'
        rows = wk._article_search(t.cur, 'create a new thing', APP, 3, 'everyone')
        # The upload pipeline strips Markdown emphasis; the words remain.
        body = rows[0][9]
        assert 'Tap New' in body and 'tap Create' in body, \
            'the whole article, every step, is returned'


def test_rendered_sections_carry_the_task():
    from endpoints import waswa_app_guide as ag
    _setup()
    text = ag.render(APP, 'Create a thing', 'Intro.\n\n## Steps\n\n1. Tap **New**.',
                     COMMIT_1, 'Make one.', ['add a thing'])
    assert '## Create a thing: Steps\n\n1. Tap **New**.' in text, text
    assert 'Also asked as: add a thing.' in text
    assert 'Make one.' in text


def test_routes_need_review_permission():
    app, *_ = _setup()
    client = app.test_client()
    assert client.get('/assistant/console/app-guide/oliwa-mobile').status_code == 401
    assert client.post('/assistant/console/app-guide/oliwa-mobile/sync',
                       json={}).status_code == 401


def main():
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith('test_') and callable(fn)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print('  ok    %s' % name)
        except Exception as error:      # noqa: BLE001
            failed += 1
            print('  FAIL  %s: %s: %s' % (name, error.__class__.__name__, error))
    print('\n%d/%d passed' % (len(tests) - failed, len(tests)))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
