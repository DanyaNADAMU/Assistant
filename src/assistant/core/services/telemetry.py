"""Operational telemetry, diagnostics, and healthcheck services for Assistant."""

import asyncio
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from assistant.adapters.storage import response_cache
from assistant.config import TaskCategory, settings
from assistant.core.ports.cache import CacheStats

# Process startup baseline
SERVICE_START_TIME = datetime.now(UTC)


class TelemetrySnapshot(BaseModel):
    """Complete snapshot of operational telemetry and system health."""

    environment: str
    uptime_seconds: float
    uptime_formatted: str
    memory_rss_mb: float
    db_size_kb: float
    wal_size_kb: float
    registered_users: int
    cache_stats: CacheStats
    active_models: dict[str, str] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def format_telegram_report(self) -> str:
        """Format the telemetry snapshot as a rich Telegram diagnostic card."""
        lines: list[str] = [
            "📊 **Диагностика и статус Assistant**\n",
            f"🟢 **Сервис**: Активен (`{self.environment}`)",
            f"⏱️ **Аптайм**: `{self.uptime_formatted}`",
            f"🧠 **Память (RSS)**: `{self.memory_rss_mb:.1f} МБ`\n",
            "⚡ **Кэширование и дедупликация (SHA-256)**:",
            f"• Саммари в базе: `{self.cache_stats.summary_count}`",
            f"• Попаданий в кэш: `{self.cache_stats.summary_hits}` (сэкономлено вызовов LLM)",
            f"• Уточнений в кэше: `{self.cache_stats.refinement_count}`",
            f"• Эффективность (Hit Rate): `{self.cache_stats.hit_rate:.1f}%`\n",
            "💾 **Хранилище данных (SQLite WAL)**:",
            f"• Размер БД: `{self.db_size_kb:.1f} КБ`",
            f"• Размер WAL: `{self.wal_size_kb:.1f} КБ`",
            f"• Пользователей с настройками: `{self.registered_users}`\n",
            "🤖 **Активная матрица моделей (OpenRouter)**:",
        ]

        for cat_name, model_name in self.active_models.items():
            lines.append(f"• `{cat_name}`: `{model_name}`")

        lines.append(f"\n—\n_Обновлено: {self.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}_")
        return "\n".join(lines)


class TelemetryService:
    """Service providing real-time diagnostics, memory tracking, and health validation."""

    def __init__(
        self,
        db_path: Path | None = None,
        started_at: datetime | None = None,
    ) -> None:
        self._db_path = db_path or settings.db_path
        self._started_at = started_at or SERVICE_START_TIME

    def get_uptime_seconds(self) -> float:
        """Calculate total elapsed uptime in seconds."""
        now = datetime.now(UTC)
        return max(0.0, (now - self._started_at).total_seconds())

    def format_uptime(self) -> str:
        """Format uptime into human-readable representation (e.g. 2д 4ч 12м 30с)."""
        seconds = int(self.get_uptime_seconds())
        days, remainder = divmod(seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, secs = divmod(remainder, 60)

        parts: list[str] = []
        if days > 0:
            parts.append(f"{days}д")
        if hours > 0 or days > 0:
            parts.append(f"{hours}ч")
        if minutes > 0 or hours > 0 or days > 0:
            parts.append(f"{minutes}м")
        parts.append(f"{secs}с")
        return " ".join(parts)

    def get_memory_usage_mb(self) -> float:
        """Return Resident Set Size (RSS) in megabytes."""
        try:
            status_file = Path("/proc/self/status")
            if status_file.exists():
                with status_file.open("r", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("VmRSS:"):
                            parts = line.split()
                            if len(parts) >= 2:
                                return float(parts[1]) / 1024.0
        except Exception:
            pass

        try:
            import resource

            rusage = resource.getrusage(resource.RUSAGE_SELF)
            return float(rusage.ru_maxrss) / 1024.0
        except Exception:
            return 0.0

    def _get_storage_stats_sync(self) -> tuple[float, float, int]:
        """Synchronously compute database sizes and user count."""
        db_size_kb = 0.0
        wal_size_kb = 0.0
        user_count = 0

        if self._db_path.exists():
            db_size_kb = self._db_path.stat().st_size / 1024.0
            wal_file = Path(f"{self._db_path}-wal")
            if wal_file.exists():
                wal_size_kb = wal_file.stat().st_size / 1024.0

            try:
                with sqlite3.connect(self._db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM user_preferences;")
                    row = cursor.fetchone()
                    if row:
                        user_count = int(row[0])
            except Exception:
                pass

        return db_size_kb, wal_size_kb, user_count

    async def collect(self) -> TelemetrySnapshot:
        """Collect and aggregate full operational snapshot asynchronously."""
        db_size_kb, wal_size_kb, user_count = await asyncio.to_thread(self._get_storage_stats_sync)
        cache_metrics = await response_cache.get_stats()

        models: dict[str, str] = {}
        for cat in TaskCategory:
            primary, _ = settings.get_models_for_category(cat)
            models[cat.value] = primary

        return TelemetrySnapshot(
            environment=settings.environment,
            uptime_seconds=self.get_uptime_seconds(),
            uptime_formatted=self.format_uptime(),
            memory_rss_mb=self.get_memory_usage_mb(),
            db_size_kb=db_size_kb,
            wal_size_kb=wal_size_kb,
            registered_users=user_count,
            cache_stats=cache_metrics,
            active_models=models,
        )

    def is_healthy(self) -> bool:
        """Perform rapid healthcheck verification."""
        try:
            # Check SQLite directory writability
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self._db_path) as conn:
                conn.execute("SELECT 1;")
            return True
        except Exception:
            return False


# Singleton service instance
telemetry_service = TelemetryService()
