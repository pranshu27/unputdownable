import time
import hashlib
from collections import OrderedDict
from typing import List, Optional
from linker_agent.utils.llm_factory import get_azure_open_ai
from linker_agent.utils.logger import configure_logger

logger = configure_logger(__file__)

class EmbeddingCache:
    """LRU cache for embeddings with rolling buffer eviction."""
    
    def __init__(self, max_size: int = 1000):
        self.cache: OrderedDict[str, List[float]] = OrderedDict()
        self.max_size = max_size
        self.hits = 0
        self.misses = 0
    
    def _get_cache_key(self, text: str, model: str) -> str:
        """Generate a cache key from text and model."""
        content = f"{model}::{text}"
        return hashlib.sha256(content.encode()).hexdigest()
    
    def get(self, text: str, model: str) -> Optional[List[float]]:
        """Retrieve embedding from cache if it exists."""
        key = self._get_cache_key(text, model)
        if key in self.cache:
            self.hits += 1
            # Move to end (most recently used)
            self.cache.move_to_end(key)
            logger.debug(
                "Cache HIT | hits=%d misses=%d hit_rate=%.2f%%",
                self.hits, self.misses, 
                100 * self.hits / (self.hits + self.misses)
            )
            return self.cache[key]
        self.misses += 1
        return None
    
    def set(self, text: str, model: str, embedding: List[float]) -> None:
        """Store embedding in cache with LRU eviction."""
        key = self._get_cache_key(text, model)
        
        # If key exists, move to end
        if key in self.cache:
            self.cache.move_to_end(key)
        
        self.cache[key] = embedding
        
        # Evict oldest if over limit
        if len(self.cache) > self.max_size:
            evicted_key = next(iter(self.cache))
            self.cache.pop(evicted_key)
            logger.debug("Cache eviction | size=%d max=%d", len(self.cache), self.max_size)
    
    def clear(self) -> None:
        """Clear the entire cache."""
        self.cache.clear()
        self.hits = 0
        self.misses = 0
        logger.info("Cache cleared")
    
    def stats(self) -> dict:
        """Return cache statistics."""
        total = self.hits + self.misses
        return {
            "size": len(self.cache),
            "max_size": self.max_size,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": self.hits / total if total > 0 else 0.0
        }


# Global cache instance
_embedding_cache = EmbeddingCache(max_size=1000)


def generate_embedding(text: str, model: str = "TE3Large", use_cache: bool = True) -> List[float]:
    """Generate an embedding for a single text (sync) with caching."""
    # Check cache first
    if use_cache:
        cached = _embedding_cache.get(text, model)
        if cached is not None:
            logger.info(
                "Embedding retrieved from cache | model=%s dim=%d",
                model, len(cached)
            )
            return cached
    
    try:
        t0 = time.time()
        response = get_azure_open_ai().embeddings.create(model=model, input=text)
        emb = response.data[0].embedding
        elapsed = time.time() - t0
        
        # Store in cache
        if use_cache:
            _embedding_cache.set(text, model, emb)
        
        logger.info(
            "Embedding generated | model=%s dim=%d time=%.3fs cached=%s",
            model, len(emb), elapsed, use_cache
        )
        return emb
    except Exception as e:
        logger.exception("Embedding generation failed | model=%s", model)
        return []


def get_cache_stats() -> dict:
    """Get current cache statistics."""
    return _embedding_cache.stats()


def clear_embedding_cache() -> None:
    """Clear the embedding cache."""
    _embedding_cache.clear()