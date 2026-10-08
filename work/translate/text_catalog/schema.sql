PRAGMA foreign_keys = ON;
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
-- Exact input snapshots make exports byte-for-byte reversible, including unknown fields.
CREATE TABLE files (path TEXT PRIMARY KEY, sha256 TEXT NOT NULL, content BLOB NOT NULL, context TEXT NOT NULL);
CREATE TABLE sources (
    id INTEGER PRIMARY KEY, sha256 TEXT NOT NULL, language TEXT NOT NULL,
    zh TEXT NOT NULL, analysis BLOB NOT NULL,
    UNIQUE(sha256, language)
);
CREATE TABLE entries (
    ref TEXT PRIMARY KEY, file_path TEXT NOT NULL REFERENCES files(path),
    ordinal INTEGER NOT NULL, source_id INTEGER NOT NULL REFERENCES sources(id),
    en TEXT, status TEXT, origin TEXT, payload TEXT NOT NULL, context TEXT NOT NULL,
    UNIQUE(file_path, ordinal)
);
CREATE INDEX entries_source ON entries(source_id);
CREATE INDEX entries_status ON entries(status);
CREATE TABLE dictionary_sources (
    id TEXT PRIMARY KEY, metadata TEXT NOT NULL
);
CREATE TABLE character_pronunciations (
    character TEXT PRIMARY KEY, candidates TEXT NOT NULL,
    source_id TEXT NOT NULL REFERENCES dictionary_sources(id)
);
-- One reading may have several sense groups; different traditional forms remain distinct.
CREATE TABLE readings (
    id TEXT PRIMARY KEY, simplified TEXT NOT NULL, traditional TEXT NOT NULL,
    pinyin_numbered TEXT NOT NULL, pinyin TEXT NOT NULL,
    source_id TEXT NOT NULL REFERENCES dictionary_sources(id)
);
CREATE INDEX readings_simplified ON readings(simplified);
CREATE INDEX readings_traditional ON readings(traditional);
CREATE TABLE senses (
    id TEXT PRIMARY KEY, reading_id TEXT NOT NULL REFERENCES readings(id),
    ordinal INTEGER NOT NULL, gloss TEXT NOT NULL
);
CREATE INDEX senses_reading ON senses(reading_id);
CREATE TABLE terms (
    id TEXT PRIMARY KEY, zh TEXT NOT NULL, en TEXT NOT NULL, scope TEXT NOT NULL,
    provenance TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE INDEX terms_zh ON terms(zh);
CREATE TABLE annotations (
    ref TEXT PRIMARY KEY REFERENCES entries(ref), source_sha256 TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('current', 'stale')), payload TEXT NOT NULL
);
-- FTS is for English/romanization. Chinese substring search uses instr(), including single hanzi.
CREATE VIRTUAL TABLE search USING fts5(ref UNINDEXED, en, pinyin);
