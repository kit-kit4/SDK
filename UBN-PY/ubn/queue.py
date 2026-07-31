import json
from pathlib import Path
from typing import Any

import aiofiles

class AsyncFileQueue:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    async def push(self, item: dict[str, Any]) -> None:
        async with aiofiles.open(self.path, "a", encoding="utf-8") as f:
            await f.write(json.dumps(item, ensure_ascii=False) + "\n")

    async def pop_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        items: list[dict[str, Any]] = []
        async with aiofiles.open(self.path, "r", encoding="utf-8") as f:
            async for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    items.append(json.loads(line))
                except Exception:
                    continue
        await self.clear()
        return items

    async def clear(self) -> None:
        async with aiofiles.open(self.path, "w", encoding="utf-8") as f:
            await f.write("")

    async def count(self) -> int:
        if not self.path.exists():
            return 0
        async with aiofiles.open(self.path, "r", encoding="utf-8") as f:
            return sum(1 async for line in f if line.strip())