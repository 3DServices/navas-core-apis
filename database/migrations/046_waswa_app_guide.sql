-- 046_waswa_app_guide.sql
--
-- App guides: how-to articles generated from an app's own source and kept in
-- step with it, published into Waswa's corpus.
--
-- Each article is an ordinary dll_waswa_sources document -- uploaded, chunked,
-- reviewed, versioned and removed through endpoints/waswa_documents.py exactly
-- like a document from the AI Console. What an ordinary document lacks is a
-- stable identity across versions: the console knows "this upload replaces
-- that one" only because a person picked it. A sync has to know it by itself,
-- so this table maps (app, slug) -- e.g. ('oliwa-mobile', 'create-geofence')
-- -- to the newest version uploaded for it.
--
--   content_hash  sha256 of the article body. The sync compares it to decide
--                 whether anything changed; an unchanged article is skipped,
--                 so re-running a sync is cheap and creates no versions.
--   app_commit    the app's git commit the article was last checked against.
--
-- Safe to run more than once.

CREATE TABLE IF NOT EXISTS dll_waswa_app_guide (
    app            VARCHAR(40)  NOT NULL,
    slug           VARCHAR(120) NOT NULL,
    title          VARCHAR(300) NOT NULL,
    source_uid     VARCHAR(64)  NOT NULL REFERENCES dll_waswa_sources (source_uid),
    content_hash   CHAR(64)     NOT NULL,
    app_commit     VARCHAR(64),
    synced_by      VARCHAR(64),
    synced_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    PRIMARY KEY (app, slug),
    CONSTRAINT dll_waswa_app_guide_slug_shape
        CHECK (slug ~ '^[a-z0-9][a-z0-9-]{1,118}[a-z0-9]$'),
    CONSTRAINT dll_waswa_app_guide_app_shape
        CHECK (app ~ '^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$')
);

CREATE INDEX IF NOT EXISTS idx_waswa_app_guide_source
    ON dll_waswa_app_guide (source_uid);

COMMENT ON TABLE dll_waswa_app_guide IS
    'App how-to articles synced into the Waswa corpus: (app, slug) -> newest '
    'uploaded version in dll_waswa_sources. See endpoints/waswa_app_guide.py.';
