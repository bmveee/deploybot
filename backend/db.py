from datetime import datetime
from enum import Enum
import json
from sqlmodel import SQLModel, Session, delete, select, create_engine, text
from typing import Any, Dict, List, Literal, Optional

from backend.config import settings
from backend.models import (
    Config,
    DeploymentRequest,
    DeploymentState,
    Deployment,
)


class ConfigDBMode(Enum):
    """Enum defining the access mode for a configuration database."""

    READ_ONLY = "read_only"
    READ_WRITE = "read_write"


class DeploymentDB:
    """
    Manages the deployments database for storing deployment metadata and current state.
    """

    def __init__(self, db_path: str = "deployments.ddb"):
        self.db_path = db_path
        self.engine = create_engine(f"duckdb:///{db_path}")

        with self.engine.connect() as conn:
            conn.execute(text("INSTALL icu;"))
            conn.execute(text("LOAD icu;"))

        SQLModel.metadata.create_all(self.engine)

    def create_deployment(
        self, request: DeploymentRequest
    ) -> Optional[int] | Literal[0]:
        """
        Create a new deployment record based on a request dict and return its ID.
        """
        deployment = Deployment(
            state=DeploymentState.INITIAL.name,
            source_env=request.source_environment,
            target_env=request.target_environment,
            deployment_payload=request.requested_configs,
        )
        with Session(self.engine) as session:
            session.add(deployment)
            session.commit()
            session.refresh(deployment)
        return deployment.id or 0

    def update_deployment_state(
        self, deployment_id: int, state: DeploymentState
    ) -> None:
        """Update the state of a deployment"""

        with Session(self.engine) as session:
            statement = select(Deployment).where(Deployment.id == deployment_id)
            result = session.exec(statement)
            deployment = result.one_or_none()
            if deployment:
                deployment.state = state.name
                deployment.updated_at = datetime.now(tz=settings.ENV_DEFAULT_TZ)
                session.add(deployment)
                session.commit()

    def update_deployment_payload(self, deployment_id: int, payload: Any) -> None:
        """
        Update the payload of a deployment.

        SQLModel will handle JSON conversion
        """

        def serialize_datetime(obj):
            if isinstance(obj, datetime):
                return {"__datetime__": obj.isoformat()}
            return obj

        payload_serialized = json.loads(json.dumps(payload, default=serialize_datetime))
        with Session(self.engine) as session:
            statement = select(Deployment).where(Deployment.id == deployment_id)
            deployment = session.exec(statement).one_or_none()
            if deployment:
                deployment.deployment_payload = payload_serialized
                deployment.updated_at = datetime.now(tz=settings.ENV_DEFAULT_TZ)
                session.add(deployment)
                session.commit()

    def update_test_results(self, deployment_id: int, test_results: List[Any]) -> None:
        """Update the test results of a deployment."""

        with Session(self.engine) as session:
            statement = select(Deployment).where(Deployment.id == deployment_id)
            deployment = session.exec(statement).one_or_none()
            if deployment:
                deployment.test_results = json.dumps(test_results)
                deployment.updated_at = datetime.now(tz=settings.ENV_DEFAULT_TZ)
                session.add(deployment)
                session.commit()

    def get_deployment(self, deployment_id: int) -> Deployment:
        """Get all information about a deployment as a Deployment object."""

        with Session(self.engine) as session:
            statement = select(Deployment).where(Deployment.id == deployment_id)
            deployment = session.exec(statement).one_or_none()
            return deployment

    def delete_all_deployments(self) -> None:
        """Delete all deployment records from the database."""

        with Session(self.engine) as session:
            session.exec(delete(Deployment))
            session.commit()

    def select_all_deployments(self) -> List[Deployment]:
        """Retrieve all deployment records."""

        with Session(self.engine) as session:
            deployments = session.exec(select(Deployment)).all()
            return deployments


class ConfigDB:
    """
    Represents a configuration database stored in a DuckDB file.
    Uses SQLModel to define and operate on the schema.
    """

    def __init__(
        self,
        db_path: str,
        mode: ConfigDBMode = ConfigDBMode.READ_WRITE,
        env_name: str = "",
    ):
        """
        Initialize a ConfigDB instance.

        Args:
            db_path: Path to the DuckDB database file.

            mode: Access mode for the database (read_only or read_write).

            env_name: Optional name of the environment (dev, prod, etc.).
        """
        self.db_path = db_path
        self.mode = mode
        self.env_name = env_name
        self.engine = create_engine(
            f"duckdb:///{db_path}",
            connect_args={"read_only": mode == ConfigDBMode.READ_ONLY},
        )

        with self.engine.connect() as conn:
            conn.execute(text("INSTALL icu;"))
            conn.execute(text("LOAD icu;"))

        SQLModel.metadata.create_all(self.engine)

    def insert_config_entry(
        self,
        config_key: str,
        value: str,
        effective_date: Optional[datetime] = None,
    ) -> None:
        """
        Insert a single configuration entry.

        Raises:
            PermissionError: If database is in read-only mode.
        """
        if self.mode == ConfigDBMode.READ_ONLY:
            raise PermissionError(f"Cannot write to database in {self.mode.value} mode")
        if effective_date is None:
            effective_date = datetime.now(settings.ENV_DEFAULT_TZ)
        config_entry = Config(
            config_key=config_key,
            value=value,
            EffectiveDate=effective_date,
        )
        with Session(self.engine) as session:
            session.add(config_entry)
            session.commit()

    def bulk_insert_config_entries(self, configs: List[Dict[str, Any]]) -> None:
        """
        Bulk inserts multiple configuration entries into the config table.

        Each dictionary in the list must contain the following keys:
            - "config_key": the configuration key.
            - "value": the configuration value.

        Optionally, a dictionary may include "EffectiveDate".

        If "EffectiveDate" is not provided, the current datetime is used.
        """
        if self.mode == ConfigDBMode.READ_ONLY:
            raise PermissionError(f"Cannot write to database in {self.mode.value} mode")
        entries = []
        for config in configs:
            key = config.get("config_key")
            val = config.get("value")

            effective_date = config.get("EffectiveDate")

            if isinstance(effective_date, dict) and "__datetime__" in effective_date:
                effective_date = datetime.fromisoformat(effective_date["__datetime__"])
            elif not effective_date:
                effective_date = datetime.now(settings.ENV_DEFAULT_TZ)

            entries.append(
                Config(config_key=key, value=val, EffectiveDate=effective_date)
            )
        with Session(self.engine) as session:
            session.add_all(entries)
            session.commit()

    def update_config_effective_date(
        self, config_key: str, new_effective_date: datetime
    ) -> None:
        """
        Update the effective date for a configuration key.
        Raises:
            PermissionError: If database is in read-only mode.
        """
        if self.mode == ConfigDBMode.READ_ONLY:
            raise PermissionError(
                f"Unable to write to database in {self.mode.value} mode"
            )
        with Session(self.engine) as session:
            statement = select(Config).where(Config.config_key == config_key)
            config_entry = session.exec(statement).one_or_none()
            if config_entry:
                config_entry.EffectiveDate = new_effective_date
                session.add(config_entry)
                session.commit()

    def get_config_by_keys(self, config_keys: List[str]) -> List[Config]:
        """
        Retrieve configuration entries for the specified keys.
        Returns a list of Config model instances.
        """
        with Session(self.engine) as session:
            statement = select(Config).where(Config.config_key.in_(config_keys))
            return session.exec(statement).all()

    def get_all_configs(self) -> List[Config]:
        """
        Retrieve all configuration entries.
        Returns a list of Config model instances.
        """
        with Session(self.engine) as session:
            return session.exec(select(Config)).all()

    def clear_all_configs(self) -> None:
        """
        Clear all configuration entries.
        Raises:
            PermissionError: If database is in read-only mode.
        """
        if self.mode == ConfigDBMode.READ_ONLY:
            raise PermissionError(f"Cannot write to database in {self.mode.value} mode")
        with Session(self.engine) as session:
            session.exec(delete(Config))
            session.commit()
