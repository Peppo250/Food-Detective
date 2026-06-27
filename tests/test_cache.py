import os
import tempfile
import time
import pytest
from food_detective.modules.cache import IngredientCache, _normalise

def test_key_normalisation():
    assert _normalise("  Sugar  ") == "sugar"
    assert _normalise("Corn   Syrup") == "corn syrup"
    assert _normalise("MSG") == "msg"

def test_cache_set_get():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_ingredients.db")
        cache = IngredientCache(db_path=db_path)
        
        test_data = {"name": "sugar", "status": "caution", "explanation": "Sweet!"}
        cache.set("Sugar", test_data)
        
        # Retrieval (case insensitive, normalises whitespaces)
        retrieved = cache.get("  sugar  ")
        assert retrieved is not None
        assert retrieved["name"] == "sugar"
        assert retrieved["status"] == "caution"
        
        # Non-existent key
        assert cache.get("salt") is None

def test_cache_expiration():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_ingredients.db")
        cache = IngredientCache(db_path=db_path)
        
        test_data = {"name": "salt", "status": "safe"}
        cache.set("salt", test_data)
        
        # Directly manipulate DB to expire the entry
        with cache._connect() as con:
            con.execute("UPDATE ingredients SET expires_at = ? WHERE key = 'salt'", (int(time.time()) - 10,))
            
        assert cache.get("salt") is None
        
        # Purge
        purged = cache.purge_expired()
        assert purged == 1
        
        stats = cache.stats()
        assert stats["total"] == 0
