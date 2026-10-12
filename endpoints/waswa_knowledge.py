"""
waswa_knowledge.py — Waswa's document retrieval (Phase 3).

Phase 2 gave Waswa tools over the product catalogue. This gives it the rest of
what the company has written down: the ecosystem scope, the user stories, the
KPI framework, the strategy papers. Product questions still go to
waswa_products — those tables are level 1 and structured, and a paragraph that
mentions a product is not the same as the product's approved record.

## Retrieval is full-text, not vector

`pg_available_extensions` has no 'vector' row on this server, so pgvector is
not installable without touching the host, and at 2,679 chunks brute-force
similarity in Python would be fast enough anyway. The embedding column in
migration 035 is reserved for that.

What keyword search is bad at showed up on the first real question asked of the
live corpus. "Who approves a discount" ranked the §26.6 approval ladder —
the passage that names Level 2 SMU/KCM and Level 3 CEO — at position 14,
because it lists four approval levels together and so mentions discounts only
twice in a long chunk. A journey-map row that repeats the word four times
outranked it. ts_rank rewards term density, and the most authoritative passage
on a subject is often the one that treats it among others.

Nothing here hand-tunes around that: the default result count is wider than it
was, and a note flags when the top hit is less authoritative than something
below it. The real fixes are embeddings and a curated-answer table, and this
query is the argument for both.

## What comes back, and what does not

  * Only approved sources, by default. A document is ingested as 'pending' and
    stays unquotable until a person approves it. `include_unapproved` exists
    for diagnosis, not for answering customers.
  * Only what the caller's audience may read. Documents are 'staff' unless
    someone marks them 'everyone' (migration 041). The audience comes from the
    server — dispatch() takes it from the caller's permissions and discards
    any the model tries to pass — so a customer cannot talk Waswa into reading
    the sales procedures to them.
  * Never level 5 or 6. Internal working material and unreviewed documents are
    excluded by vw_waswa_retrievable via may_quote. Waswa does not get to
    decide that an internal sales strategy paper is fine to read out.
  * The full chunk, not a snippet. Waswa is being asked to answer from this
    text; a 200-character extract with the qualifying sentence cut off is how a
    correct source produces a wrong answer.
  * Every result carries its authority level and its source, so the caller
    records real evidence rather than a flat "level 1" for everything.

## Empty is an answer

A search that finds nothing returns `found: false` with the reason — no
approved documents at all, versus approved documents that do not cover this.
Those are different problems and Waswa should say which one it hit.
"""

import re

import psycopg2
from flask import current_app

# Six, not four. The first real question asked of the live corpus — "who
# approves a discount" — put the chunk that actually answers it ("No discounts
# unless approved by SMU/KCM") at rank 6, behind a journey-map row that merely
# repeats the word. Four results is a tighter prompt and a worse answer.
_DEFAULT_LIMIT = 6
_MAX_LIMIT = 8
_MAX_TOTAL_CHARS = 7000     # across all returned chunks, to bound prompt cost

# A floor on the combined text-and-authority score. Below it a match is one
# incidental word in a 1,500-character chunk, and returning it invites an answer
# built from text that is not about the question.
_MIN_SCORE = 0.01

_FIELDS = (
    "chunk_uid, source_uid, heading_path, page_from, page_to, body, "
    "authority_level, authority_label, document_type, source_title, "
    "version_label, document_date, product_uid, category, review_status"
)


def _connect():
    return psycopg2.connect(current_app.config.get('waswa_db_link') or current_app.config['db_link'])


_FIELD_COUNT = 15       # _FIELDS above; the score is appended after them


def _row(record):
    (chunk_uid, source_uid, heading, page_from, page_to, body, level, label,
     doc_type, title, version, date, product_uid, category, review) = \
        record[:_FIELD_COUNT]
    score = record[_FIELD_COUNT]
    return {
        'chunk_uid': chunk_uid,
        'heading': heading,
        'text': body,
        'source': title,
        'source_ref': ' '.join(filter(None, (title, version))),
        'document_type': doc_type,
        'pages': (f'{page_from}-{page_to}' if page_from and page_to
                  and page_from != page_to else (page_from or None)),
        'authority_level': level,
        'authority': label,
        'document_date': str(date) if date else None,
        'product_uid': product_uid,
        'category': category,
        'review_status': review,
        'score': round(float(score), 4),
    }


def _terms(text):
    """Words worth searching for, for the OR fallback."""
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'\-]{2,}", text or '')
    return [w for w in words if w.lower() not in _STOPWORDS][:12]


_STOPWORDS = {
    'the', 'and', 'for', 'are', 'you', 'your', 'our', 'can', 'how', 'what',
    'why', 'who', 'when', 'where', 'with', 'from', 'does', 'did', 'was',
    'were', 'has', 'have', 'had', 'that', 'this', 'there', 'they', 'them',
    'about', 'into', 'will', 'would', 'should', 'could', 'been', 'being',
    'get', 'got', 'tell', 'show', 'give', 'need', 'want', 'know', 'any',
    'all', 'not', 'but', 'its', 'his', 'her', 'their', 'more', 'than',
    'and/or', 'let', 'please', 'also', 'just', 'like', 'some', 'many',
    'much', 'very', 'out', 'off', 'per', 'via', 'was', 'were', 'mine',
}


def _audiences(audience):
    return ['staff', 'everyone'] if audience == 'staff' else ['everyone']


def _search(cur, query, filters, limit, include_unapproved,
            audience='everyone'):
    """Try progressively looser queries; return (rows, how_matched)."""
    where = ["c.search_vector @@ q", "c.audience = ANY(%(audiences)s)"]
    params = {'audiences': _audiences(audience)}

    if not include_unapproved:
        where.append("c.review_status = 'approved'")
    if filters.get('product_uid'):
        where.append("c.product_uid = %(product_uid)s")
        params['product_uid'] = filters['product_uid']
    if filters.get('document_type'):
        where.append("c.document_type = %(document_type)s")
        params['document_type'] = filters['document_type']
    if filters.get('app_guide'):
        # The guide's newest version of each article, and the version it
        # replaces: while a new version awaits review the old one is still
        # the live one, and the article must not vanish from search for that
        # window. vw_waswa_retrievable drops whichever of the two is not live.
        where.append(
            "c.source_uid IN ("
            " SELECT g.source_uid FROM dll_waswa_app_guide g"
            "  WHERE g.app = %(app_guide)s"
            " UNION"
            " SELECT s.replaces_source_uid FROM dll_waswa_app_guide g"
            "  JOIN dll_waswa_sources s ON s.source_uid = g.source_uid"
            "  WHERE g.app = %(app_guide)s AND s.replaces_source_uid IS NOT NULL)")
        params['app_guide'] = filters['app_guide']
    if filters.get('max_authority_level'):
        where.append("c.authority_level <= %(max_authority_level)s")
        params['max_authority_level'] = filters['max_authority_level']

    # Authority multiplies the text score rather than sorting before it. Sorting
    # by authority first would surface a level-3 chunk that barely mentions the
    # subject above a level-4 chunk that answers the question; multiplying keeps
    # relevance in charge while still preferring the more authoritative of two
    # comparable matches.
    def build(query_expr, extra_where):
        return (
            f"SELECT {_FIELDS}, "
            f"       ts_rank_cd(c.search_vector, q, 32) "
            f"         * ((7 - c.authority_level)::numeric / 6) AS score "
            f"FROM vw_waswa_retrievable c, {query_expr} AS q "
            f"WHERE {' AND '.join(where + extra_where)} "
            f"  AND ts_rank_cd(c.search_vector, q, 32) "
            f"        * ((7 - c.authority_level)::numeric / 6) >= {_MIN_SCORE} "
            f"ORDER BY score DESC, c.authority_level ASC LIMIT %(limit)s")

    params['limit'] = limit
    params['q'] = query

    attempts = [
        ('phrase', "websearch_to_tsquery('english', %(q)s)", []),
        ('words', "plainto_tsquery('english', %(q)s)", []),
    ]

    # The loose tier, and the one that needs a leash. An OR of every term will
    # match something for any question at all: "how do I claim my pension"
    # matched four chunks on the word "claim" alone and came back looking like
    # an answer. That is the failure this whole build exists to prevent — a
    # confident response assembled from text that is not about the question.
    #
    # So the OR tier additionally requires a minimum number of the query's
    # distinctive terms to be present, counted by PostgreSQL against each term
    # separately so that stemming still applies ("KPIs" finds "KPI").
    terms = _terms(query)
    if terms:
        counters, needed = [], {}
        for index, term in enumerate(terms):
            key = f't{index}'
            counters.append(
                f"(c.search_vector @@ plainto_tsquery('english', %({key})s))::int")
            needed[key] = term
        params.update(needed)
        params['min_terms'] = min(len(terms), max(2, (len(terms) + 1) // 2))
        attempts.append((
            'several terms',
            "to_tsquery('english', %(or_terms)s)",
            [f"({' + '.join(counters)}) >= %(min_terms)s"]))
        params['or_terms'] = ' | '.join(
            re.sub(r"[^A-Za-z0-9]", ' ', t).strip().replace(' ', '') or 'x'
            for t in terms)

    for how, expr, extra in attempts:
        cur.execute(build(expr, extra), params)
        rows = cur.fetchall() if cur.rowcount > 0 else []
        if rows:
            return rows, how
    return [], None


def _corpus_state(cur, audience='everyone'):
    """Why a search found nothing — the cases are not the same problem."""
    cur.execute("SELECT COUNT(*) FROM dll_waswa_chunks")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM vw_waswa_retrievable "
                "WHERE review_status = 'approved'")
    approved = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM vw_waswa_retrievable "
                "WHERE review_status = 'approved' AND audience = ANY(%s)",
                (_audiences(audience),))
    visible = cur.fetchone()[0]
    return total, approved, visible


def knowledge_search(query, product=None, document_type=None, limit=None,
                     include_unapproved=False, audience='everyone',
                     app_guide=None):
    """Search approved company documents for text answering a question.

    app_guide narrows the search to one app's synced guide (see
    waswa_app_guide). It is how app_guide_search is built, not a filter the
    model is told about.
    """
    query = (query or '').strip()
    if not query:
        return {'found': False, 'reason': 'no query given', 'results': []}

    limit = min(int(limit or _DEFAULT_LIMIT), _MAX_LIMIT)
    conn = _connect()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            filters = {'document_type': document_type,
                       'app_guide': app_guide}
            notes = []

            if product:
                cur.execute(
                    "SELECT product_uid FROM abi_products_manager "
                    "WHERE LOWER(product_name) = LOWER(%s) "
                    "UNION ALL "
                    "SELECT product_uid FROM abi_product_aliases "
                    "WHERE LOWER(alias) = LOWER(%s) LIMIT 1", (product, product))
                if cur.rowcount:
                    filters['product_uid'] = cur.fetchone()[0]
                else:
                    notes.append(
                        f"'{product}' is not an approved product name, so the "
                        f"search was not narrowed to it")

            rows, how = _search(cur, query, filters, limit, include_unapproved,
                                audience)

            # The model chooses document_type itself, and guesses: "what
            # happens when a SIM goes offline?" was searched as a "procedure"
            # when the only document covering it is a specification, and the
            # filter turned an answerable question into "not covered". A wrong
            # guess at the type must not hide the answer, so widen once -- and
            # say so, as for an unknown product.
            if not rows and filters.get('document_type'):
                widened = dict(filters, document_type=None)
                rows, how = _search(cur, query, widened, limit,
                                    include_unapproved, audience)
                if rows:
                    notes.append(
                        f"nothing of type '{document_type}' matched, so these "
                        f"results come from other document types")

            if not rows:
                total, approved, visible = _corpus_state(cur, audience)
                if not total:
                    reason = ('the knowledge corpus is empty — no documents '
                              'have been ingested')
                elif not approved and not include_unapproved:
                    reason = (f'{total} chunks are stored but none has been '
                              f'approved for customer-facing answers yet')
                elif not visible and not include_unapproved:
                    # Say it without naming what exists: that there are
                    # internal documents is fine to know, their titles are not.
                    reason = ('no company documents have been released for '
                              'customers yet, so there is nothing to search '
                              'on their behalf. Offer to connect them with '
                              'support rather than answering from memory')
                else:
                    reason = ('the approved documents do not cover this. Note '
                              'that search is keyword-based, so a question '
                              'phrased differently from the documents may miss')
                return {'found': False, 'reason': reason, 'results': [],
                        'notes': notes}

            results, used = [], 0
            for record in rows:
                item = _row(record)
                if used + len(item['text']) > _MAX_TOTAL_CHARS and results:
                    notes.append('more matches were found than fit in one '
                                 'result set; narrow the question to see them')
                    break
                used += len(item['text'])
                results.append(item)

            if how != 'phrase':
                notes.append(f'matched on {how}, not the exact phrase — read '
                             f'each result before relying on it')
            levels = {r['authority_level'] for r in results}
            if levels and min(levels) >= 4:
                notes.append('these are specification documents: they say what '
                             'is designed, not what is live for this account')
            # When the top hit is less authoritative than something below it,
            # say so. ts_rank rewards term density, so a passage that repeats a
            # word can outrank the procedure that decides the matter — and the
            # model has no way to see that from the order alone.
            if len(results) > 1:
                best = results[0]['authority_level']
                stronger = [r for r in results[1:]
                            if r['authority_level'] < best]
                if stronger:
                    notes.append(
                        f"the highest-scoring result is authority level {best}, "
                        f"but result(s) below it come from level "
                        f"{min(r['authority_level'] for r in stronger)} "
                        f"({stronger[0]['source']}) — prefer the more "
                        f"authoritative source where they disagree")

            if len({r['source'] for r in results}) == 1:
                notes.append(f"all results come from one document "
                             f"({results[0]['source']}) — nothing else in the "
                             f"corpus corroborates this")

            return {'found': True, 'matched_on': how, 'count': len(results),
                    'results': results, 'notes': notes}
    finally:
        conn.close()


def knowledge_sources(document_type=None, audience='everyone'):
    """What documents Waswa can draw on. Use it to answer honestly about scope."""
    conn = _connect()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            # Quotable levels only. A title is content: "Operation WOW — Oil &
            # Gas Clients Strategy Paper" read out to a customer is a leak even
            # if no line of it is quoted, so an internal document is not listed
            # here any more than it is searched.
            sql = ("SELECT title, document_type, authority_level, "
                   "       authority_label, authority_confirmed, review_status, "
                   "       chunk_count "
                   "FROM vw_waswa_corpus "
                   "WHERE authority_level IN ("
                   "    SELECT authority_level FROM dll_waswa_authority_levels "
                   "    WHERE may_quote = TRUE) "
                   "  AND source_uid IN (SELECT source_uid FROM dll_waswa_sources "
                   "                     WHERE audience = ANY(%s))")
            params = [_audiences(audience)]
            if document_type:
                sql += " AND document_type = %s"
                params.append(document_type)
            cur.execute(sql, params)
            rows = cur.fetchall() if cur.rowcount > 0 else []

            documents = [
                {'title': r[0], 'document_type': r[1], 'authority_level': r[2],
                 'authority': r[3], 'authority_confirmed': r[4],
                 'quotable': r[5] == 'approved', 'chunks': r[6]}
                for r in rows
            ]
            quotable = [d for d in documents if d['quotable']]

            # Why the list is empty matters: "nothing uploaded" and "uploaded
            # but not visible to this reader" look identical from outside, and
            # the old note talked about "the titles above" when there were none.
            notes = []
            if documents and not quotable:
                notes.append(
                    'No document is approved yet, so knowledge_search will '
                    'return nothing. Say you do not have it in approved '
                    'information; do not answer from the titles above.')
            elif not documents:
                cur.execute("SELECT COUNT(*) FROM dll_waswa_sources WHERE active = TRUE")
                loaded = cur.fetchone()[0]
                if not loaded:
                    notes.append('No documents have been uploaded yet, so '
                                 'knowledge_search will return nothing.')
                else:
                    cur.execute(
                        "SELECT COUNT(*) FROM dll_waswa_sources "
                        "WHERE active = TRUE AND NOT (audience = ANY(%s))",
                        (_audiences(audience),))
                    hidden = cur.fetchone()[0]
                    cur.execute(
                        "SELECT COUNT(*) FROM dll_waswa_sources WHERE active = TRUE "
                        "AND authority_level NOT IN (SELECT authority_level "
                        "FROM dll_waswa_authority_levels WHERE may_quote = TRUE)")
                    unquotable = cur.fetchone()[0]
                    why = []
                    if hidden:
                        why.append(f'{hidden} visible to staff only')
                    if unquotable:
                        why.append(f'{unquotable} at an authority level that may not be quoted')
                    notes.append(
                        f'{loaded} document(s) are loaded, but none can be '
                        f'read to a "{audience}" reader'
                        + (' (' + ', '.join(why) + ')' if why else '')
                        + ', so knowledge_search will return nothing.')

            return {
                'documents': documents,
                'total': len(documents),
                'quotable': len(quotable),
                'audience': audience,
                'notes': notes,
            }
    finally:
        conn.close()


# ── Tool specifications ─────────────────────────────────────────────────────

TOOL_SPECS = [
    {
        'type': 'function',
        'function': {
            'name': 'knowledge_search',
            'description': (
                'Search approved company documents — ecosystem scope, user '
                'stories, KPI definitions, strategy — for text that answers a '
                'question. Use this for how something works, what a term '
                'means, what a module is for, or what is in scope. Do NOT use '
                'it for a specific product\'s approved record (use '
                'product_lookup) or for anything about this account (that is '
                'already in the context). Returns found: false with a reason '
                'when the approved documents do not cover the question.'),
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {
                        'type': 'string',
                        'description': (
                            'The question, in the words the documents would '
                            'use. Search is keyword-based, so include the '
                            'terms likely to appear in the document.')},
                    'product': {
                        'type': 'string',
                        'description': (
                            'Narrow to one product, e.g. OLIWA, UKO. Omit '
                            'unless the question is clearly about one.')},
                    'document_type': {
                        'type': 'string',
                        'description': (
                            'strategy | user_stories | kpi | procedure. '
                            'Omit unless the question names a kind of '
                            'document.')},
                    'limit': {'type': 'integer',
                              'description': 'Results to return, 1-8. Default 4.'},
                },
                'required': ['query'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'app_guide_search',
            'description': (
                'Step-by-step instructions for doing something in the OLIWA '
                'mobile app: which screen, which button, what to enter, what '
                'happens next. Use this FIRST for any "how do I ...", "where '
                'is ...", "why can\'t I ..." question about using the app. '
                'It searches only the app guide, which is kept in step with '
                'the app itself. Returns found: false when the guide does not '
                'cover it.'),
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {
                        'type': 'string',
                        'description': (
                            'What the person wants to do, in the words the '
                            'app uses, e.g. "add a vehicle", "top up tokens", '
                            '"export a trip report".')},
                    'limit': {'type': 'integer',
                              'description': 'Results to return, 1-8. Default 4.'},
                },
                'required': ['query'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'knowledge_sources',
            'description': (
                'List the approved documents available to search, with their '
                'authority level. Use when asked what you know about, or '
                'before saying something is not documented, so the answer '
                'names what was actually checked.'),
            'parameters': {
                'type': 'object',
                'properties': {
                    'document_type': {'type': 'string'},
                },
            },
        },
    },
]

APP_GUIDE_APP = 'oliwa-mobile'


# Where a question's words are found in an app-guide article, and what each
# place is worth. One article is one task, so what names the task counts most:
#   title + "Also asked as" phrasings   1.0  ("Create a geofence", "add a geofence")
#   rest of the opening (summary)       0.5
#   section headings                    0.25
#   body                                0.1
# Each distinct question word counts once per place -- coverage, not
# frequency. ts_rank counted repeats, so an article whose title and three
# phrasings all say "vehicle" beat the one whose phrasing was the question.
# A title or phrasing that contains the question as a phrase adds 1.0.
_ARTICLE_PLACE_WEIGHTS = (('lead', 1.0), ('opening_vec', 0.5),
                          ('heading_vec', 0.25), ('body_vec', 0.1))
_ARTICLE_MAX_CHARS = 6000
_ARTICLE_DEFAULT_LIMIT = 3


def _article_search(cur, query, app, limit, audience):
    """Rank whole app-guide articles, not chunks.

    Chunk ranking failed these articles in a specific way: the words that say
    WHICH task an article is about sit in its title and opening, while its
    steps sit in another chunk, and proximity scoring inside the long steps
    chunk drowned them -- "create a new geofence" ranked the Edit article,
    whose body happens to contain that phrase, above the Create article. An
    article is short and is one task, so it is ranked as one document and
    returned whole, which also gives the model every step, in order.

    A match needs at least half of the question's distinctive terms (two,
    for questions of two or more) somewhere in the article. One shared word
    is not enough: "fix my car engine" matched "Track a vehicle live" on
    "car" alone.
    """
    terms = _terms(query)
    if terms:
        # Words PostgreSQL ignores ("now", "where") can never match, so they
        # must not count toward the words a match needs: "where is my vehicle
        # now" needed two of {vehicle, now} and could only ever find one.
        cur.execute("SELECT t FROM unnest(%s::text[]) AS t "
                    "WHERE plainto_tsquery('english', t)::text <> ''", (terms,))
        searchable = {r[0] for r in cur.fetchall()}
        terms = [t for t in terms if t in searchable]
    if not terms:
        return []
    or_terms = ' | '.join(
        re.sub(r"[^A-Za-z0-9]", ' ', t).strip().replace(' ', '') or 'x'
        for t in terms)
    need = min(len(terms), max(2, (len(terms) + 1) // 2))
    term_hits = ' + '.join(
        f"(a.doc @@ plainto_tsquery('english', %(t{i})s))::int"
        for i in range(len(terms)))
    coverage = ' + '.join(
        f"{weight} * (a.{place} @@ plainto_tsquery('english', %(t{i})s))::int"
        for place, weight in _ARTICLE_PLACE_WEIGHTS
        for i in range(len(terms)))
    params = {'app': app, 'audiences': _audiences(audience), 'q': or_terms,
              'phrase': query, 'need': need, 'limit': limit}
    params.update({f't{i}': t for i, t in enumerate(terms)})
    cur.execute(f"""
        WITH chunks AS (
            SELECT c.* FROM vw_waswa_retrievable c
            WHERE c.review_status = 'approved'
              AND c.audience = ANY(%(audiences)s)
              AND c.source_uid IN (
                  SELECT g.source_uid FROM dll_waswa_app_guide g
                   WHERE g.app = %(app)s
                  UNION
                  SELECT s.replaces_source_uid FROM dll_waswa_app_guide g
                    JOIN dll_waswa_sources s ON s.source_uid = g.source_uid
                   WHERE g.app = %(app)s AND s.replaces_source_uid IS NOT NULL)
        ), articles AS (
            SELECT source_uid, source_title, authority_level, authority_label,
                   document_type, version_label, document_date, category,
                   review_status,
                   string_agg(body, E'\n\n' ORDER BY ordinal) AS body,
                   string_agg(coalesce(heading_path, ''), ' ' ORDER BY ordinal)
                       AS headings,
                   max(body) FILTER (WHERE ordinal = 1) AS opening
            FROM chunks
            GROUP BY source_uid, source_title, authority_level,
                     authority_label, document_type, version_label,
                     document_date, category, review_status
        ), a AS (
            SELECT articles.*,
                   to_tsvector('english', source_title || ' ' ||
                       coalesce(substring(opening
                                from 'Also asked as: ([^\\n]*)'), '')) AS lead,
                   to_tsvector('english', coalesce(opening, '')) AS opening_vec,
                   to_tsvector('english', headings) AS heading_vec,
                   to_tsvector('english', body) AS body_vec,
                   to_tsvector('english', source_title || ' ' ||
                       coalesce(opening, '') || ' ' || headings || ' ' || body)
                       AS doc
            FROM articles
        )
        SELECT a.source_uid, a.source_title, a.authority_level,
               a.authority_label, a.document_type, a.version_label,
               a.document_date, a.category, a.review_status, a.body,
               ({coverage})
               + (a.lead @@ phraseto_tsquery('english', %(phrase)s))::int
               + 0.01 * ts_rank(a.doc, to_tsquery('english', %(q)s)) AS score
        FROM a
        WHERE ({term_hits}) >= %(need)s
        ORDER BY score DESC
        LIMIT %(limit)s""", params)
    return cur.fetchall() if cur.rowcount > 0 else []


def app_guide_search(query, limit=None, audience='everyone'):
    """Search the OLIWA mobile app's own guide, and nothing else.

    Separate from knowledge_search on purpose. Asked how to do something in
    the app, a general search ranks the CMS manual -- 54 passages on
    geofences, all of them about a different application -- above anything
    about the app, and the model then presents CMS steps as app steps. This
    tool cannot return them. It returns whole articles; see _article_search.
    """
    query = (query or '').strip()
    if not query:
        return {'found': False, 'reason': 'no query given', 'results': []}
    limit = max(1, min(int(limit or _ARTICLE_DEFAULT_LIMIT), _MAX_LIMIT))
    conn = _connect()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            rows = _article_search(cur, query, APP_GUIDE_APP, limit, audience)
    finally:
        conn.close()
    if not rows:
        return {'found': False, 'results': [], 'notes': [], 'reason': (
            'The OLIWA mobile app guide does not cover this. Do not answer '
            'with steps from another application (such as the NAVAS CMS) as '
            'if they were app steps; say the app guide does not cover it and '
            'offer who can help.')}
    results = []
    for (source_uid, title, level, label, doc_type, version, doc_date,
         category, review, body, score) in rows:
        text = body if len(body) <= _ARTICLE_MAX_CHARS else (
            body[:_ARTICLE_MAX_CHARS] + '\n[...]')
        results.append({
            'chunk_uid': f'{source_uid}-article',
            'heading': title,
            'text': text,
            'source': title,
            'source_ref': ' '.join(filter(None, (title, version))),
            'document_type': doc_type,
            'pages': None,
            'authority_level': level,
            'authority': label,
            'document_date': str(doc_date) if doc_date else None,
            'product_uid': None,
            'category': category,
            'review_status': review,
            'score': round(float(score), 4),
        })
    notes = ['each result is a whole app guide article: give its steps in '
             'order, with the app\'s own labels']
    if len(results) > 1 and results[1]['score'] >= 0.8 * results[0]['score']:
        notes.append('more than one article matches closely; if the question '
                     'could mean either task, ask which one they mean')
    return {'found': True, 'matched_on': 'article', 'count': len(results),
            'results': results, 'notes': notes}


_DISPATCH = {
    'knowledge_search': knowledge_search,
    'knowledge_sources': knowledge_sources,
    'app_guide_search': app_guide_search,
}


def dispatch(tool_name, arguments, audience='everyone'):
    """Run a knowledge tool. [audience] comes from the server, never the model:
    anything the model passes for audience or include_unapproved is dropped."""
    func = _DISPATCH.get(tool_name)
    if not func:
        return None
    arguments = {k: v for k, v in (arguments or {}).items()
                 if k not in ('audience', 'include_unapproved')}
    try:
        return func(**arguments, audience=audience)
    except TypeError as error:
        return {'error': f'bad arguments for {tool_name}: {error}'}
    except Exception as error:      # noqa: BLE001 - never break the turn
        return {'error': f'{tool_name} failed: {error}'}


def authority_of(result):
    """The authority level to record as evidence for a knowledge result.

    The weakest level among the returned chunks, not the strongest: an answer
    built from a level 3 and a level 4 chunk is only as good as the level 4
    one, and evidence that claims otherwise is worse than no evidence.
    """
    if not isinstance(result, dict):
        return None
    levels = [r.get('authority_level') for r in result.get('results') or []
              if r.get('authority_level') is not None]
    return max(levels) if levels else None
