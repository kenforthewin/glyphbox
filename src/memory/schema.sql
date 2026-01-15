-- Memory System Database Schema
-- SQLite schema for persistent game state and cross-episode learning

-- Episodes table: tracks individual game sessions
CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id TEXT UNIQUE NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    end_reason TEXT,  -- 'death', 'ascension', 'quit', 'timeout'
    final_score INTEGER DEFAULT 0,
    final_turns INTEGER DEFAULT 0,
    final_depth INTEGER DEFAULT 0,
    final_xp_level INTEGER DEFAULT 0,
    death_reason TEXT,
    skills_used INTEGER DEFAULT 0,
    skills_created INTEGER DEFAULT 0,
    metadata TEXT,  -- JSON for additional data
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_episodes_started ON episodes(started_at);
CREATE INDEX IF NOT EXISTS idx_episodes_score ON episodes(final_score);

-- Dungeon levels table: explored level data
CREATE TABLE IF NOT EXISTS dungeon_levels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id TEXT NOT NULL,
    level_number INTEGER NOT NULL,
    branch TEXT DEFAULT 'main',  -- 'main', 'mines', 'sokoban', 'gehennom', etc.
    first_visited_turn INTEGER,
    last_visited_turn INTEGER,
    tiles_explored INTEGER DEFAULT 0,
    total_tiles INTEGER DEFAULT 0,
    upstairs_x INTEGER,
    upstairs_y INTEGER,
    downstairs_x INTEGER,
    downstairs_y INTEGER,
    has_altar INTEGER DEFAULT 0,
    altar_alignment TEXT,
    has_shop INTEGER DEFAULT 0,
    shop_type TEXT,
    has_fountain INTEGER DEFAULT 0,
    has_sink INTEGER DEFAULT 0,
    tile_data TEXT,  -- Compressed/serialized tile grid
    features TEXT,   -- JSON list of special features
    metadata TEXT,   -- JSON for additional data
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (episode_id) REFERENCES episodes(episode_id),
    UNIQUE(episode_id, level_number, branch)
);

CREATE INDEX IF NOT EXISTS idx_levels_episode ON dungeon_levels(episode_id);
CREATE INDEX IF NOT EXISTS idx_levels_number ON dungeon_levels(level_number);

-- Stashes table: remembered item locations
CREATE TABLE IF NOT EXISTS stashes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id TEXT NOT NULL,
    level_number INTEGER NOT NULL,
    branch TEXT DEFAULT 'main',
    position_x INTEGER NOT NULL,
    position_y INTEGER NOT NULL,
    items TEXT NOT NULL,  -- JSON list of item descriptions
    turn_discovered INTEGER,
    turn_last_seen INTEGER,
    still_exists INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (episode_id) REFERENCES episodes(episode_id)
);

CREATE INDEX IF NOT EXISTS idx_stashes_episode ON stashes(episode_id);
CREATE INDEX IF NOT EXISTS idx_stashes_level ON stashes(level_number, branch);

-- Discovered items table: item identification tracking
CREATE TABLE IF NOT EXISTS discovered_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id TEXT NOT NULL,
    appearance TEXT NOT NULL,  -- 'red potion', 'scroll labeled ELAM EBOW'
    true_identity TEXT,        -- 'potion of healing', 'scroll of identify'
    object_class TEXT,         -- 'potion', 'scroll', 'wand', etc.
    buc_status TEXT,           -- 'blessed', 'uncursed', 'cursed', NULL if unknown
    turn_discovered INTEGER,
    discovery_method TEXT,     -- 'use', 'shop', 'identify', 'altar'
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (episode_id) REFERENCES episodes(episode_id),
    UNIQUE(episode_id, appearance, object_class)
);

CREATE INDEX IF NOT EXISTS idx_items_episode ON discovered_items(episode_id);
CREATE INDEX IF NOT EXISTS idx_items_appearance ON discovered_items(appearance);

-- Monster encounters table: track monster sightings
CREATE TABLE IF NOT EXISTS monster_encounters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id TEXT NOT NULL,
    monster_name TEXT NOT NULL,
    level_number INTEGER,
    branch TEXT,
    position_x INTEGER,
    position_y INTEGER,
    turn_seen INTEGER,
    outcome TEXT,  -- 'killed', 'fled', 'peaceful', 'tamed', NULL if ongoing
    damage_dealt INTEGER DEFAULT 0,
    damage_taken INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (episode_id) REFERENCES episodes(episode_id)
);

CREATE INDEX IF NOT EXISTS idx_monsters_episode ON monster_encounters(episode_id);
CREATE INDEX IF NOT EXISTS idx_monsters_name ON monster_encounters(monster_name);

-- Events table: significant game events
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id TEXT NOT NULL,
    turn INTEGER NOT NULL,
    event_type TEXT NOT NULL,  -- 'death', 'levelup', 'found_item', 'killed_monster', etc.
    description TEXT,
    level_number INTEGER,
    branch TEXT,
    position_x INTEGER,
    position_y INTEGER,
    data TEXT,  -- JSON for event-specific data
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (episode_id) REFERENCES episodes(episode_id)
);

CREATE INDEX IF NOT EXISTS idx_events_episode ON events(episode_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_turn ON events(turn);

-- Cross-episode learning: monster danger ratings
CREATE TABLE IF NOT EXISTS monster_knowledge (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    monster_name TEXT UNIQUE NOT NULL,
    encounters INTEGER DEFAULT 0,
    kills INTEGER DEFAULT 0,
    deaths_caused INTEGER DEFAULT 0,
    avg_damage_dealt REAL DEFAULT 0,
    avg_damage_taken REAL DEFAULT 0,
    danger_rating REAL DEFAULT 0.5,  -- 0.0 (safe) to 1.0 (deadly)
    notes TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_monster_knowledge_name ON monster_knowledge(monster_name);
CREATE INDEX IF NOT EXISTS idx_monster_knowledge_danger ON monster_knowledge(danger_rating);

-- Cross-episode learning: item usefulness ratings
CREATE TABLE IF NOT EXISTS item_knowledge (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_name TEXT UNIQUE NOT NULL,
    object_class TEXT,
    times_used INTEGER DEFAULT 0,
    times_helpful INTEGER DEFAULT 0,
    times_harmful INTEGER DEFAULT 0,
    usefulness_rating REAL DEFAULT 0.5,  -- 0.0 (useless/harmful) to 1.0 (very useful)
    notes TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_item_knowledge_name ON item_knowledge(item_name);

-- Schema version for migrations
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Insert initial schema version
INSERT OR IGNORE INTO schema_version (version) VALUES (1);
