from datetime import datetime
from enum import Enum, auto
from pydantic import BaseModel
from sqlalchemy import DateTime
from sqlmodel import JSON, Column, Integer, SQLModel, Field, Sequence
from typing import List, Optional, Any

from backend.config import settings

class Deployment(SQLModel, table=True):
    __tablename__ = "deployments"
    id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, Sequence("seq_deployment_id"), primary_key=True),
    )
    state: str
    source_env: str
    target_env: str
    deployment_payload: List[Any] = Field(
        sa_column=Column(JSON, nullable=False)
    )
    test_results: Optional[str] = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=settings.ENV_DEFAULT_TZ)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=settings.ENV_DEFAULT_TZ)
    )


class Config(SQLModel, table=True):
    __tablename__ = "config"
    config_key: str = Field(primary_key=True)
    value: str
    EffectiveDate: datetime = Field(
        default_factory=lambda: datetime.now(tz=settings.ENV_DEFAULT_TZ),
        sa_column=Column("EffectiveDate", DateTime(timezone=True), nullable=False),
    )


class DeploymentState(Enum):
    INITIAL = auto()
    CHANGES_SELECTED = auto()
    TESTS_RUN = auto()
    REVIEW = auto()
    APPROVED = auto()
    DEPLOYED = auto()
    DEPLOYMENT_FAILED = auto()


class DeploymentRequest(BaseModel):
    requested_configs: List[str]
    source_environment: str
    target_environment: str
