"""
Hybrid Caching System: LRU + SQLite Persistence
Provides persistent caching that survives server restarts
"""

import sqlite3
import json
from collections import OrderedDict
from pathlib import Path
import time
from typing import Any, Optional


class HybridCache:
    """LRU + SQLite persistent caching system
    
    Two-tier caching:
    - Tier 1: In-memory LRU (fast, <1ms)
    - Tier 2: SQLite persistence (survives restart)
    """
    
    def __init__(self, cache_size: int = 1000, db_path: str = 'semantic_cache.db'):
        """Initialize hybrid cache
        
        Args:
            cache_size: Maximum LRU entries (default 1000)
            db_path: Path to SQLite database file
        """
        self.lru_cache = OrderedDict()
        self.max_size = cache_size
        self.db_path = Path(db_path)
        
        self._init_db()
        self._load_from_db()
        print(f"[CACHE] HybridCache initialized: {cache_size} LRU + SQLite at {db_path}")
    
    def _init_db(self) -> None:
        """Create SQLite database for persistence"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS cache (
                        key TEXT PRIMARY KEY,
                        value BLOB NOT NULL,
                        timestamp INTEGER NOT NULL,
                        hits INTEGER DEFAULT 0
                    )
                ''')
                conn.commit()
        except Exception as e:
            print(f"[CACHE-ERROR] Database init failed: {e}")
    
    def _load_from_db(self) -> None:
        """Load cache from disk on startup"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    'SELECT key, value FROM cache ORDER BY hits DESC LIMIT ?',
                    (self.max_size,)
                )
                for key, value in cursor.fetchall():
                    self.lru_cache[key] = json.loads(value)
            print(f"[CACHE] Loaded {len(self.lru_cache)} entries from SQLite")
        except Exception as e:
            print(f"[CACHE-WARN] Error loading cache: {e}")
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache (LRU → DB → None)"""
        # Check LRU first (fastest: <1ms)
        if key in self.lru_cache:
            self.lru_cache.move_to_end(key)
            self._update_hits(key)
            return self.lru_cache[key]
        
        # Check database (slower: 10-50ms)
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('SELECT value FROM cache WHERE key = ?', (key,))
                row = cursor.fetchone()
                if row:
                    value = json.loads(row[0])
                    self.lru_cache[key] = value
                    self._evict_if_full()
                    self._update_hits(key)
                    return value
        except Exception as e:
            print(f"[CACHE-ERROR] DB read failed: {e}")
        
        return None
    
    def set(self, key: str, value: Any) -> None:
        """Set value in cache (LRU + DB)"""
        self.lru_cache[key] = value
        self._evict_if_full()
        self._persist_to_db(key, value)
    
    def _persist_to_db(self, key: str, value: Any) -> None:
        """Save to SQLite for persistence"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT OR REPLACE INTO cache (key, value, timestamp) 
                    VALUES (?, ?, ?)
                ''', (key, json.dumps(value, default=str), int(time.time())))
                conn.commit()
        except Exception as e:
            print(f"[CACHE-ERROR] DB write failed: {e}")
    
    def _update_hits(self, key: str) -> None:
        """Track hit count"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('UPDATE cache SET hits = hits + 1 WHERE key = ?', (key,))
                conn.commit()
        except Exception as e:
            print(f"[CACHE-ERROR] Hit update failed: {e}")
    
    def _evict_if_full(self) -> None:
        """Evict least recently used item if full"""
        if len(self.lru_cache) > self.max_size:
            self.lru_cache.popitem(last=False)
    
    def clear_expired(self, days: int = 7) -> None:
        """Clear entries older than N days"""
        try:
            cutoff_time = int(time.time()) - (days * 86400)
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    'DELETE FROM cache WHERE timestamp < ?',
                    (cutoff_time,)
                )
                conn.commit()
                print(f"[CACHE] Cleared {cursor.rowcount} expired entries")
        except Exception as e:
            print(f"[CACHE-ERROR] Cleanup failed: {e}")
    
    def stats(self) -> dict:
        """Get cache statistics"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('SELECT COUNT(*), SUM(hits) FROM cache')
                total, total_hits = cursor.fetchone()
                
            return {
                'lru_size': len(self.lru_cache),
                'db_size': total or 0,
                'total_hits': total_hits or 0
            }
        except Exception as e:
            print(f"[CACHE-ERROR] Stats failed: {e}")
            return {}
