-- Research from a goal: the author describes what they need (an article, a series of posts),
-- the AI plans the search, TALeport collects evergreen material (Wikipedia, Reddit, YouTube,
-- video transcripts, documents, the user's chat with web search) and builds a dossier.

CREATE TABLE research_projects (
    id          INTEGER PRIMARY KEY,
    goal        TEXT NOT NULL,
    title       TEXT NOT NULL DEFAULT '',
    languages   TEXT NOT NULL DEFAULT '["it"]', -- JSON: languages to search in
    plan        TEXT,                           -- JSON: questions, keywords, queries
    dossier     TEXT,                           -- JSON: notions, rules, examples, ...
    article     TEXT,                           -- JSON: the last article written from it
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE research_sources (
    id          INTEGER PRIMARY KEY,
    project_id  INTEGER NOT NULL REFERENCES research_projects(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL,     -- wikipedia, reddit, youtube, video, document, text, web
    title       TEXT NOT NULL DEFAULT '',
    url         TEXT NOT NULL DEFAULT '',
    author      TEXT NOT NULL DEFAULT '',
    language    TEXT,
    content     TEXT NOT NULL DEFAULT '',  -- article text, post, transcript, document
    digest      TEXT,                      -- JSON: goal-focused summary (points)
    status      TEXT NOT NULL DEFAULT 'ready', -- found, queued, processing, ready, error
    step        TEXT,                      -- download, transcribe, summary (videos)
    error_code  TEXT,
    meta        TEXT NOT NULL DEFAULT '{}', -- JSON: duration, channel, views, ...
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX idx_research_sources_project ON research_sources(project_id);
