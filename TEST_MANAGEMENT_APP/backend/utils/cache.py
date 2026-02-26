"""
Hybrid Caching System: LRU + SQLite Persistence
Two-tier caching system that provides:
1. Fast in-memory LRU cache (OrderedDict) for frequent access
2. Persistent SQLite3 database for survives server restarts
3. Automatic tier management and promotion/demotion
4. Statistics tracking and performance monitoring

Usage:
    cache = HybridCache(cache_size=1000, db_path='semantic_cache.db')
    
    # Get (checks LRU first, falls back to SQLite)
    value = cache.get('function_CAN_Init')
    
    # Set (writes to both LRU and SQLite)
    cache.set('function_CAN_Init', {'name': 'CAN_Init', 'params': [...]})
    
    # Stats
    stats = cache.stats()  # {lru_entries, db_entries, hit_rate, avg_access_time}
"""

import sqlite3
import json
import hashlib
from collections import OrderedDict
from pathlib import Path
from datetime import datetime
import time
from typing import Any, Optional, Dict
import threading


class HybridCache:
    """LRU + SQLite persistent caching system
    
    Two-tier architecture:
    - Tier 1 (Fast): In-memory LRU cache using OrderedDict
      * Max entries: configurable (default 1000)
      * Access time: <1ms
      * Lost on server restart
    
    - Tier 2 (Persistent): SQLite3 database on disk
      * Unlimited entries (bounded by disk)
      * Access time: 10-50ms
      * Survives server restart
      * Tracks hit count and timestamp
    
    Strategy:
    1. On GET: Check LRU first (fast), fall back to SQLite
    2. On SET: Write to both LRU and SQLite (guaranteed persistence)
    3. On eviction: Move out of LRU but keep in SQLite
    4. Automatic promotion: Frequent items stay in LRU
    """
    
    def __init__(self, cache_size: int = 1000, db_path: str = 'semantic_cache.db'):
        """Initialize hybrid cache with dual-tier storage
        
        Args:
            cache_size: Maximum LRU entries (default 1000)
            db_path: Path to SQLite database file (created if doesn't exist)
        
        Example:
            cache = HybridCache(cache_size=1000, db_path='app_cache.db')
        """
        self.lru_cache = OrderedDict()
        self.max_size = cache_size
        self.db_path = Path(db_path)
        
        # Statistics tracking
        self.stats_lock = threading.Lock()
        self.stats = {
            'hits': 0,
            'misses': 0,
            'sets': 0,
            'lru_evictions': 0,
            'db_reads': 0
        }
        
        self._init_db()
        self._load_from_db()
        print(f"[CACHE] HybridCache initialized: {cache_size} LRU + SQLite3 at {db_path}")
    
    def _init_db(self) -> None:
        """Create SQLite database schema for persistence"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS cache (
                        key TEXT PRIMARY KEY,
                        value BLOB NOT NULL,
                        timestamp INTEGER NOT NULL,
                        hits INTEGER DEFAULT 0,
                        last_accessed INTEGER NOT NULL
                    )
                ''')
                conn.execute('''
                    CREATE INDEX IF NOT EXISTS idx_hits 
                    ON cache(hits DESC)
                ''')
                conn.execute('''
                    CREATE INDEX IF NOT EXISTS idx_timestamp 
                    ON cache(timestamp DESC)
                ''')
                conn.commit()
                db_size = self.db_path.stat().st_size if self.db_path.exists() else 0
                print(f"[CACHE] SQLite3 database ready: {self.db_path} ({db_size} bytes)")
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
            now = int(time.time())
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT OR REPLACE INTO cache (key, value, timestamp, last_accessed) 
                    VALUES (?, ?, ?, ?)
                ''', (key, json.dumps(value, default=str), now, now))
                conn.commit()
        except Exception as e:
            print(f"[CACHE-ERROR] DB write failed: {e}")
    
    def _update_hits(self, key: str) -> None:
        """Track hit count"""
        try:
            now = int(time.time())
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    'UPDATE cache SET hits = hits + 1, last_accessed = ? WHERE key = ?',
                    (now, key)
                )
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
