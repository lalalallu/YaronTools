import hashlib
from typing import Optional


class ConflictDetector:
    def __init__(self):
        self._original_hash: Optional[str] = None

    def record_state(self, raw_bytes: bytes):
        self._original_hash = hashlib.md5(raw_bytes).hexdigest()

    def check_conflict(self, current_raw_bytes: bytes) -> bool:
        if self._original_hash is None:
            return False
        current_hash = hashlib.md5(current_raw_bytes).hexdigest()
        return current_hash != self._original_hash

    def update_state(self, raw_bytes: bytes):
        self._original_hash = hashlib.md5(raw_bytes).hexdigest()

    def reset(self):
        self._original_hash = None
