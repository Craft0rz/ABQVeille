"""
Execution State Tracking

Tracks pipeline execution state for recovery and reporting.
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any
import json


class PipelineStage(Enum):
    """Pipeline execution stages."""
    INITIALIZED = "initialized"
    RSS_FETCH = "rss_fetch"
    CONTENT_EXTRACT = "content_extract"
    RELEVANCY_SCORE = "relevancy_score"
    EMAIL_GENERATE = "email_generate"
    EMAIL_SEND = "email_send"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class StageResult:
    """Result of a single pipeline stage."""
    stage: PipelineStage
    success: bool
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: float = 0.0
    items_processed: int = 0
    error: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionState:
    """Tracks complete pipeline execution state."""
    date_str: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    current_stage: PipelineStage = PipelineStage.INITIALIZED
    stages: List[StageResult] = field(default_factory=list)
    success: bool = False
    exit_code: int = 1
    error_message: Optional[str] = None

    # Metrics
    total_articles_fetched: int = 0
    relevant_articles: int = 0
    emails_sent: int = 0
    emails_failed: int = 0

    def start_stage(self, stage: PipelineStage) -> StageResult:
        """Start tracking a new stage."""
        self.current_stage = stage
        result = StageResult(stage=stage, success=False, started_at=datetime.now())
        self.stages.append(result)
        return result

    def complete_stage(
        self,
        result: StageResult,
        success: bool,
        items: int = 0,
        error: str = None,
        details: dict = None
    ):
        """Mark a stage as complete."""
        result.completed_at = datetime.now()
        result.success = success
        result.items_processed = items
        result.duration_seconds = (result.completed_at - result.started_at).total_seconds()
        result.error = error
        if details:
            result.details = details

    def mark_complete(self, success: bool, exit_code: int = 0):
        """Mark entire execution as complete."""
        self.completed_at = datetime.now()
        self.success = success
        self.exit_code = exit_code
        self.current_stage = PipelineStage.COMPLETED if success else PipelineStage.FAILED

    def get_duration(self) -> float:
        """Get total execution duration in seconds."""
        end = self.completed_at or datetime.now()
        return (end - self.started_at).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "date": self.date_str,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.get_duration(),
            "success": self.success,
            "exit_code": self.exit_code,
            "current_stage": self.current_stage.value,
            "error_message": self.error_message,
            "metrics": {
                "articles_fetched": self.total_articles_fetched,
                "relevant_articles": self.relevant_articles,
                "emails_sent": self.emails_sent,
                "emails_failed": self.emails_failed
            },
            "stages": [
                {
                    "name": s.stage.value,
                    "success": s.success,
                    "duration_seconds": s.duration_seconds,
                    "items_processed": s.items_processed,
                    "error": s.error
                }
                for s in self.stages
            ]
        }

    def save(self, path: Path):
        """Save execution state to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: Path) -> Optional['ExecutionState']:
        """Load execution state from JSON file."""
        if not path.exists():
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            state = cls(
                date_str=data['date'],
                started_at=datetime.fromisoformat(data['started_at'])
            )
            state.success = data['success']
            state.exit_code = data['exit_code']
            return state
        except Exception:
            return None
