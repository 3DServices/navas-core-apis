"""
waswa_documents.py — upload, version, approve and remove Waswa's documents
from the AI Console (migration 042).

Until now a document reached Waswa through a developer: convert it with a
script, add it to manifest.json, run the ingest script, approve it from the
command line. This module does the same steps behind one upload, with the same
rules:

  * Converted to text the same way the scripts do it — pdf_to_knowledge_md for
    PDFs, xlsx_to_knowledge_md for workbooks, gdoc_to_knowledge_md's cleaner for
    text — and chunked by ingest_waswa_knowledge.chunk_document, so a document
    uploaded here is split exactly like one loaded from the command line.
    .docx is read directly from its XML, so no extra package is needed.
  * Currency amounts are withheld before anything is stored. Waswa never states
    prices, and the pricing block has to hold for what staff upload too.
  * Nothing is searchable until approved, and not by the person who uploaded
    it.
  * A new version does not replace the old one until it is approved. Until
    then Waswa keeps answering from the old version.
  * Remove is reversible. The rows stay, so an answer given last month can
    still be traced to what it was read from.

Every function takes the caller's cursor and does not commit.
"""

import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import uuid
import zipfile
from xml.etree import ElementTree

from flask import current_app

from .waswa_answers import RuleError, log

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
ALLOWED = {'.pdf', '.docx', '.xlsx', '.md', '.txt'}
UPLOADABLE_LEVELS = (2, 3, 4, 5, 6)   # level 1 is structured product data only
DOCUMENT_TYPES = ('procedure', 'policy', 'manual', 'faq', 'strategy',
                  'user_stories', 'kpi', 'journey_map', 'catalogue', 'other')

_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'scripts')
_modules = {}


def _script(name):
    """Import one of the scripts/ converters by path (scripts is not a package)."""
    if name not in _modules:
        spec = importlib.util.spec_from_file_location(
            f'waswa_{name}', os.path.join(_SCRIPTS, f'{name}.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _modules[name] = module
    return _modules[name]


def upload_readiness():
    """What this server can accept right now, so the console can say so up
    front instead of failing on the first upload."""
    root = upload_root()
    try:
        os.makedirs(root, exist_ok=True)
        writable = os.access(root, os.W_OK)
    except OSError:
        writable = False
    return {
        'pdf': importlib.util.find_spec('pdfplumber') is not None,
        'xlsx': importlib.util.find_spec('openpyxl') is not None,
        'storage_writable': writable,
        'storage_path': os.path.abspath(root),
    }


def upload_root():
    return current_app.config.get('WASWA_UPLOAD_DIR') or os.path.join(
        'database', 'knowledge', 'uploads')


# ── Conversion ─────────────────────────────────────────────────────────────

_W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


def _docx_to_markdown(data, title):
    """Headings, paragraphs, list items and tables from a .docx, in order."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            xml = archive.read('word/document.xml')
    except (zipfile.BadZipFile, KeyError):
        raise RuleError('This .docx could not be opened. Save it again from '
                        'Word or Google Docs and re-upload.')
    body = ElementTree.fromstring(xml).find(f'{_W}body')
    out = [f'# {title}', '']

    def text_of(node):
        parts = []
        for element in node.iter():
            if element.tag == f'{_W}t' and element.text:
                parts.append(element.text)
            elif element.tag in (f'{_W}tab',):
                parts.append(' ')
            elif element.tag in (f'{_W}br', f'{_W}cr'):
                parts.append('\n')
        return ''.join(parts).strip()

    for block in list(body) if body is not None else []:
        if block.tag == f'{_W}p':
            text = text_of(block)
            if not text:
                continue
            style = block.find(f'{_W}pPr/{_W}pStyle')
            style = (style.get(f'{_W}val') if style is not None else '') or ''
            level = re.search(r'(?i)heading\s*([1-6])', style)
            if style.lower() == 'title':
                out += [f'## {text}', '']
            elif level:
                out += [f"{'#' * min(6, int(level.group(1)) + 1)} {text}", '']
            elif block.find(f'{_W}pPr/{_W}numPr') is not None:
                out.append(f'- {text}')
            else:
                out += [text, '']
        elif block.tag == f'{_W}tbl':
            rows = []
            for row in block.iter(f'{_W}tr'):
                cells = [text_of(c).replace('\n', ' ').replace('|', '/')
                         for c in row.iter(f'{_W}tc')]
                if any(cells):
                    rows.append(cells)
            if rows:
                width = max(len(r) for r in rows)
                rows = [r + [''] * (width - len(r)) for r in rows]
                out.append('| ' + ' | '.join(rows[0]) + ' |')
                out.append('|' + ' --- |' * width)
                out += ['| ' + ' | '.join(r) + ' |' for r in rows[1:]]
                out.append('')
    return '\n'.join(out)


def _pdf_to_markdown(path, title):
    try:
        converter = _script('pdf_to_knowledge_md')
    except ImportError:
        raise RuleError('PDF uploads need the pdfplumber package on the '
                        'server. Run: pip install pdfplumber — then restart '
                        'the API.', 503)
    try:
        markdown, _stats, _pages = converter.convert(path, title)
    except SystemExit as stop:
        raise RuleError(f'{stop} Upload a PDF with selectable text, or a '
                        f'.docx version of it.')
    return markdown


def _xlsx_to_markdown(path, title):
    converter = _script('xlsx_to_knowledge_md')
    import openpyxl
    workbook = openpyxl.load_workbook(path, data_only=True)
    out = [f'# {title}', '']
    for worksheet in workbook.worksheets:
        table, rows, cols = converter.grid(worksheet)
        if not rows:
            continue
        lines, _count = converter.render(worksheet, converter.detect(table, rows, cols))
        out += lines
    return '\n'.join(out)


def _text_to_markdown(data, title):
    raw = data.decode('utf-8', errors='replace')
    stripped = raw.lstrip()
    if stripped[:1] in '{[':
        try:
            payload = json.loads(raw)
            if isinstance(payload, dict):
                for key in ('fileContent', 'content', 'text', 'body'):
                    if isinstance(payload.get(key), str):
                        raw = payload[key]
                        break
        except ValueError:
            pass
    text = _script('gdoc_to_knowledge_md').clean(raw)
    if not re.match(r'^#\s', text):
        text = f'# {title}\n\n{text}'
    return text


def to_markdown(filename, data, title, workdir):
    """(markdown, withheld_amounts) for an uploaded file."""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED:
        raise RuleError(f'{ext or "This file type"} is not supported. Upload '
                        f'PDF, Word (.docx), Excel (.xlsx), Markdown or text.')
    path = os.path.join(workdir, 'original' + ext)
    with open(path, 'wb') as handle:
        handle.write(data)

    if ext == '.pdf':
        markdown = _pdf_to_markdown(path, title)
    elif ext == '.docx':
        markdown = _docx_to_markdown(data, title)
    elif ext == '.xlsx':
        markdown = _xlsx_to_markdown(path, title)
    else:
        markdown = _text_to_markdown(data, title)

    markdown = re.sub(r'\n{3,}', '\n\n', markdown).strip() + '\n'
    markdown, withheld = _script('gdoc_to_knowledge_md').redact_currency(markdown)
    return markdown, withheld


# ── Upload ─────────────────────────────────────────────────────────────────

def _level(value, default=None):
    try:
        level = int(value)
    except (TypeError, ValueError):
        if default is not None:
            return default
        raise RuleError('Choose an authority level.')
    if level not in UPLOADABLE_LEVELS:
        raise RuleError('Authority level must be 2 to 6. Level 1 is reserved '
                        'for the structured product catalogue.')
    return level


def _clean(value, limit=None):
    text = (value or '').strip() if isinstance(value, str) else value
    return (text[:limit] if limit and isinstance(text, str) else text) or None


def _title_from(filename):
    """'sales_procedures-v26.pdf' -> 'Sales Procedures v26'."""
    stem = re.sub(r'[_\-]+', ' ', os.path.splitext(filename)[0]).strip()
    words = [w[:1].upper() + w[1:] if w.islower() and not re.match(r'^v\d', w) else w
             for w in stem.split()]
    return ' '.join(words)[:300] or 'Untitled document'


def get_source(cur, source_uid, lock=False):
    cur.execute(
        "SELECT source_uid, title, document_type, authority_level, "
        "       version_label, document_date, country_scope, review_status, "
        "       audience, active, superseded_by, replaces_source_uid, "
        "       chunk_count, ingested_by, ingested_at, reviewed_by, "
        "       reviewed_at, original_filename, stored_path, redactions, "
        "       removed_by, removed_at, removed_reason, notes "
        "FROM dll_waswa_sources WHERE source_uid = %s"
        + (" FOR UPDATE" if lock else ""), (str(source_uid),))
    row = cur.fetchone() if cur.rowcount else None
    if not row:
        raise RuleError('No such document.', 404)
    keys = ('source_uid', 'title', 'document_type', 'authority_level',
            'version_label', 'document_date', 'country_scope', 'review_status',
            'audience', 'active', 'superseded_by', 'replaces_source_uid',
            'chunk_count', 'ingested_by', 'ingested_at', 'reviewed_by',
            'reviewed_at', 'original_filename', 'stored_path', 'redactions',
            'removed_by', 'removed_at', 'removed_reason', 'notes')
    item = dict(zip(keys, row))
    for key in ('document_date', 'ingested_at', 'reviewed_at', 'removed_at'):
        if item[key] is not None:
            item[key] = item[key].isoformat()
    return item


def upload(cur, who, filename, data, form):
    """Convert, redact, chunk and store an uploaded document as 'pending'."""
    if not data:
        raise RuleError('The file is empty.')
    if len(data) > MAX_UPLOAD_BYTES:
        raise RuleError(f'The file is larger than '
                        f'{MAX_UPLOAD_BYTES // (1024 * 1024)} MB.')
    filename = os.path.basename(filename or 'document')

    replaces = _clean(form.get('replaces_source_uid'))
    previous = None
    if replaces:
        previous = get_source(cur, replaces)
        if not previous['active']:
            raise RuleError('That document has been removed. Restore it '
                            'first, or upload this as a new document.', 409)
        if previous['superseded_by']:
            raise RuleError('That document has already been replaced by a '
                            'newer version. Upload against the newest one.', 409)
        cur.execute("SELECT title FROM dll_waswa_sources "
                    "WHERE replaces_source_uid = %s AND active = TRUE "
                    "AND review_status = 'pending'", (replaces,))
        if cur.rowcount:
            raise RuleError('A new version of this document is already waiting '
                            'for review. Approve, reject or remove that one '
                            'first.', 409)

    title = _clean(form.get('title'), 300) or (previous or {}).get('title') \
        or _title_from(filename)
    document_type = _clean(form.get('document_type'), 48) \
        or (previous or {}).get('document_type') or 'other'
    if document_type not in DOCUMENT_TYPES:
        raise RuleError(f"Document type must be one of: {', '.join(DOCUMENT_TYPES)}.")
    level = _level(form.get('authority_level'),
                   (previous or {}).get('authority_level'))
    audience = _clean(form.get('audience')) or 'staff'
    if audience not in ('staff', 'everyone'):
        raise RuleError("Who can see it must be 'staff' or 'everyone'.")

    ingest = _script('ingest_waswa_knowledge')
    staging = os.path.join(upload_root(), '_incoming', uuid.uuid4().hex)
    os.makedirs(staging, exist_ok=True)
    try:
        markdown, withheld = to_markdown(filename, data, title, staging)
        chunks = ingest.chunk_document(markdown)
        if not chunks:
            raise RuleError('No readable text was found in this file. If it is '
                            'a scan, it needs OCR first.')

        # The hash of the uploaded bytes, not of the converted text: the same
        # file uploaded under a different title is still the same document.
        file_hash = hashlib.sha256(data).hexdigest()
        cur.execute("SELECT source_uid, title, active FROM dll_waswa_sources "
                    "WHERE file_hash = %s", (file_hash,))
        if cur.rowcount:
            existing_uid, existing_title, active = cur.fetchone()
            raise RuleError(
                f'This exact document is already loaded as "{existing_title}"'
                + ('' if active else ' (removed — restore it instead)') + '.',
                409)

        source_uid = 'WK-' + file_hash[:20]
        target = os.path.join(upload_root(), source_uid)
        if os.path.exists(target):
            shutil.rmtree(target)
        shutil.move(staging, target)
        staging = None
        with open(os.path.join(target, 'content.md'), 'w', encoding='utf-8') as handle:
            handle.write(markdown)
        original = next((f for f in os.listdir(target) if f.startswith('original')), None)
        if original:
            os.replace(os.path.join(target, original), os.path.join(target, filename))

        cur.execute(
            "INSERT INTO dll_waswa_sources "
            "(source_uid, title, filename, document_type, authority_level, "
            " version_label, document_date, country_scope, language, file_hash, "
            " chunk_count, ingested_by, notes, audience, replaces_source_uid, "
            " original_filename, stored_path, redactions) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'en',%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (source_uid, title, f'upload/{source_uid}.md', document_type, level,
             _clean(form.get('version_label'), 60),
             _clean(form.get('document_date')) or None,
             _clean(form.get('country_scope'), 160), file_hash, len(chunks),
             who['account_uid'], _clean(form.get('notes')), audience,
             replaces, filename, target, len(withheld)))

        written = 0
        for ordinal, (heading, page_from, page_to, body) in enumerate(chunks, 1):
            cur.execute(
                "INSERT INTO dll_waswa_chunks "
                "(chunk_uid, source_uid, ordinal, heading_path, page_from, "
                " page_to, body, char_count, content_hash, authority_level, "
                " document_type, country_scope, language) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'en') "
                "ON CONFLICT (source_uid, content_hash) DO NOTHING",
                (f'{source_uid}-{ordinal:05d}', source_uid, ordinal,
                 (heading or '')[:500] or None, page_from, page_to, body,
                 len(body), ingest.sha256(ingest.normalise(body)), level,
                 document_type, _clean(form.get('country_scope'), 160)))
            written += cur.rowcount
        cur.execute("UPDATE dll_waswa_sources SET chunk_count = %s "
                    "WHERE source_uid = %s", (written, source_uid))
    finally:
        if staging and os.path.exists(staging):
            shutil.rmtree(staging, ignore_errors=True)

    log(cur, who, 'knowledge_change',
        'document_version_uploaded' if replaces else 'document_uploaded',
        f'{title} ({filename}) — {written} passages, awaiting review',
        {'source_uid': source_uid, 'replaces': replaces,
         'withheld_amounts': len(withheld)})

    result = get_source(cur, source_uid)
    result['withheld'] = withheld[:20]
    result['preview'] = [
        {'heading': h, 'text': b[:400]} for h, _a, _b, b in chunks[:5]]
    return result


# ── Review, remove, restore, edit ──────────────────────────────────────────

def review(cur, who, source_uid, decision, note=None):
    decision = {'approve': 'approved', 'reject': 'rejected'}.get(decision, decision)
    if decision not in ('approved', 'rejected', 'pending'):
        raise RuleError("decision must be approve or reject.")
    doc = get_source(cur, source_uid, lock=True)
    if not doc['active']:
        raise RuleError('This document has been removed. Restore it first.', 409)
    if decision == 'approved' and doc['ingested_by'] == who['account_uid']:
        raise RuleError('You uploaded this document, so someone else has to '
                        'approve it.', 403)
    if decision == 'rejected' and doc['review_status'] == 'pending' and not _clean(note):
        raise RuleError('Say why it is rejected, so the uploader can fix it.')

    cur.execute("UPDATE dll_waswa_sources SET review_status=%s, reviewed_by=%s, "
                "reviewed_at=NOW(), updated_at=NOW() WHERE source_uid=%s",
                (decision, who['account_uid'], str(source_uid)))

    replaced = None
    if decision == 'approved' and doc['replaces_source_uid']:
        # The moment the new version goes live, the old one stops answering.
        cur.execute("UPDATE dll_waswa_sources SET superseded_by=%s, updated_at=NOW() "
                    "WHERE source_uid=%s AND superseded_by IS NULL RETURNING title",
                    (str(source_uid), doc['replaces_source_uid']))
        replaced = cur.fetchone()[0] if cur.rowcount else None

    log(cur, who, 'approval', f'document_{decision}',
        _clean(note) or f"{doc['title']}: {decision}"
        + (f' (replaces {replaced})' if replaced else ''),
        {'source_uid': str(source_uid), 'replaced': doc['replaces_source_uid']})
    result = get_source(cur, source_uid)
    result['replaced_title'] = replaced
    return result


def remove(cur, who, source_uid, reason):
    if not _clean(reason):
        raise RuleError('Say why it is being removed.')
    doc = get_source(cur, source_uid, lock=True)
    if not doc['active']:
        return doc
    cur.execute("UPDATE dll_waswa_sources SET active=FALSE, removed_by=%s, "
                "removed_at=NOW(), removed_reason=%s, updated_at=NOW() "
                "WHERE source_uid=%s",
                (who['account_uid'], _clean(reason), str(source_uid)))
    cur.execute("SELECT COUNT(*) FROM dll_waswa_answers "
                "WHERE based_on_source_uid=%s AND needs_recheck", (str(source_uid),))
    flagged = cur.fetchone()[0]
    log(cur, who, 'override', 'document_removed', _clean(reason),
        {'source_uid': str(source_uid), 'title': doc['title'],
         'corrections_flagged': flagged})
    result = get_source(cur, source_uid)
    result['corrections_flagged'] = flagged
    return result


def restore(cur, who, source_uid):
    doc = get_source(cur, source_uid, lock=True)
    if doc['active']:
        return doc
    if doc['superseded_by']:
        raise RuleError('A newer version of this document is live. Remove '
                        'that one instead of restoring this.', 409)
    cur.execute("UPDATE dll_waswa_sources SET active=TRUE, removed_by=NULL, "
                "removed_at=NULL, removed_reason=NULL, updated_at=NOW() "
                "WHERE source_uid=%s", (str(source_uid),))
    log(cur, who, 'override', 'document_restored', doc['title'],
        {'source_uid': str(source_uid)})
    return get_source(cur, source_uid)


_EDITABLE = ('title', 'document_type', 'authority_level', 'version_label',
             'document_date', 'country_scope', 'notes')


def update_details(cur, who, source_uid, fields):
    doc = get_source(cur, source_uid, lock=True)
    changes = {}
    for key in _EDITABLE:
        if key not in fields:
            continue
        value = fields[key]
        if key == 'authority_level':
            value = _level(value)
        elif key == 'document_type':
            value = _clean(value)
            if value not in DOCUMENT_TYPES:
                raise RuleError(f"Document type must be one of: {', '.join(DOCUMENT_TYPES)}.")
        else:
            value = _clean(value, 300)
        if key == 'title' and not value:
            raise RuleError('A document needs a title.')
        changes[key] = value
    if not changes:
        return doc

    sets = ', '.join(f'{k} = %s' for k in changes)
    cur.execute(f"UPDATE dll_waswa_sources SET {sets}, updated_at = NOW() "
                f"WHERE source_uid = %s", list(changes.values()) + [str(source_uid)])
    # Chunks carry these denormalised; retrieval reads them from the chunk.
    chunk_fields = {k: v for k, v in changes.items()
                    if k in ('authority_level', 'document_type', 'country_scope')}
    if chunk_fields:
        sets = ', '.join(f'{k} = %s' for k in chunk_fields)
        cur.execute(f"UPDATE dll_waswa_chunks SET {sets}, updated_at = NOW() "
                    f"WHERE source_uid = %s",
                    list(chunk_fields.values()) + [str(source_uid)])
    log(cur, who, 'knowledge_change', 'document_details_changed',
        f"{doc['title']}: {', '.join(changes)} changed",
        {'source_uid': str(source_uid),
         'before': {k: doc.get(k) for k in changes},
         'after': {k: (str(v) if v is not None else None) for k, v in changes.items()}})
    return get_source(cur, source_uid)


def detail(cur, source_uid, limit=40):
    doc = get_source(cur, source_uid)
    cur.execute("SELECT ordinal, heading_path, page_from, page_to, "
                "LEFT(body, 600), char_count FROM dll_waswa_chunks "
                "WHERE source_uid = %s ORDER BY ordinal LIMIT %s",
                (str(source_uid), int(limit)))
    doc['passages'] = [
        {'ordinal': r[0], 'heading': r[1], 'pages': (f'{r[2]}-{r[3]}' if r[2] and r[3] and r[2] != r[3] else r[2]),
         'text': r[4], 'chars': r[5]}
        for r in (cur.fetchall() if cur.rowcount > 0 else [])]
    cur.execute("SELECT source_uid, title, review_status, active, ingested_at "
                "FROM dll_waswa_sources WHERE replaces_source_uid = %s "
                "ORDER BY ingested_at DESC", (str(source_uid),))
    doc['newer_versions'] = [
        {'source_uid': r[0], 'title': r[1], 'review_status': r[2],
         'active': r[3], 'ingested_at': r[4].isoformat()}
        for r in (cur.fetchall() if cur.rowcount > 0 else [])]
    cur.execute("SELECT COUNT(*) FROM dll_waswa_answers "
                "WHERE based_on_source_uid = %s AND status = 'approved'",
                (str(source_uid),))
    doc['corrections_relying'] = cur.fetchone()[0]
    return doc


def authority_levels(cur):
    cur.execute("SELECT authority_level, label, description, may_quote, confirmed "
                "FROM dll_waswa_authority_levels ORDER BY authority_level")
    return [{'level': r[0], 'label': r[1], 'description': r[2],
             'may_quote': r[3], 'confirmed': r[4],
             'uploadable': r[0] in UPLOADABLE_LEVELS}
            for r in (cur.fetchall() if cur.rowcount > 0 else [])]
