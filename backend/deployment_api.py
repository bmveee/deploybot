from pprint import pprint
from typing import Any, Dict, List, Literal, Optional

from backend.models import DeploymentRequest, DeploymentState
from backend.db import ConfigDB, DeploymentDB


class Deployment:
    """
    Represents a deployment instance with state and selected changes.
    """

    def __init__(
        self,
        deployment_id: int,
        state: DeploymentState,
        changes: Optional[List[tuple]] = None,
    ):
        self.deployment_id = deployment_id
        self.state = state
        self.changes = changes if changes is not None else []
        self.errors: List[str] = []
        self.review_notes: str = ""


class DeploymentManager:
    def __init__(
        self, source_db: ConfigDB, target_db: ConfigDB, current_deployment: int | Literal[0] = 0
    ):
        self.deployment_db = DeploymentDB()
        self.source_db: ConfigDB = source_db
        self.target_db: ConfigDB = target_db
        self.current_deployment: int | Literal[0] = current_deployment
        self.errors: List[str] = []

    def create_deployment(self, request: DeploymentRequest) -> None:
        self.current_deployment = self.deployment_db.create_deployment(request)

        return None

    def select_changes(self, deployment_id: int, request: DeploymentRequest):
        """
        Selects changes from the source database based on requested keys.

        Args:
            request (DeploymentRequest): The deployment request object containing requested keys.

        Returns:
            List[dict]: A list of dictionaries representing the selected changes
        Raises:
            ValueError or Exception: If no valid payload is avilable based on key selection or deployment payload fails to update
        """
        deployment_payload = [
            config.model_dump()
            for config in self.source_db.get_config_by_keys(request.requested_configs)
        ]

        if not deployment_payload:
            raise ValueError(
                f"Deployment failure => no changes found in source database[{self.source_db.env_name}]: {deployment_payload=}"
            )

        try:
            self.deployment_db.update_deployment_payload(
                deployment_id=deployment_id, payload=deployment_payload
            )
            self.deployment_db.update_deployment_state(
                deployment_id=deployment_id, state=DeploymentState.CHANGES_SELECTED
            )
        except Exception as e:
            _error = f"Deployment failure => error updating deployment payload: {e}"
            self.errors.append(_error)
            self.deployment_db.update_deployment_state(
                deployment_id=deployment_id, state=DeploymentState.DEPLOYMENT_FAILED
            )
            raise Exception(_error)

        return deployment_payload

    def run_tests(self, deployment_id: int = 0) -> None:
        """
        Run validation tests on the selected configuration changes.

        Args:
            deployment_id: The ID of the deployment

        Raises:
            ValueError: If deployment is not in CHANGES_SELECTED state
        """
        deployment = self.deployment_db.get_deployment(
            deployment_id=deployment_id or self.current_deployment
        )

        if DeploymentState[deployment.state] != DeploymentState.CHANGES_SELECTED:
            raise ValueError(
                f"Deployment failure => cannot run tests in deployment state: {deployment.state}"
            )
        validation_results = DeploymentManager.validate_config_entries(
            deployment.deployment_payload
        )
        if validation_results:
            self.errors.extend(validation_results)
            self.deployment_db.update_test_results(
                deployment_id=deployment_id or self.current_deployment,
                test_results=validation_results,
            )
            raise ValueError("Deployment failure => invalid configuration entries")

        self.deployment_db.update_deployment_state(
            deployment_id=deployment_id or self.current_deployment,
            state=DeploymentState.TESTS_RUN,
        )

        return

    @classmethod
    def validate_config_entries(cls, entries: List[Dict[str, Any]]) -> List:
        """
        Validates that each dictionary in the list has non-empty values for all keys.

        Args:
            entries: List of configuration dictionaries.

        Returns:
            A list of bad_values - either empty list or list of dictionaries containing
                bad key / value combinations
        """
        bad_values = []
        for i, entry in enumerate(entries):
            for key, value in entry.items():
                if value is None or (isinstance(value, str) and not value.strip()):
                    bad_values.append(
                        f"Entry {i} has a None or empty value for key '{key}'."
                    )
        return bad_values

    def get_current_state(self, deployment_id: int = 0):
        deployment = self.deployment_db.get_deployment(
            deployment_id=deployment_id if deployment_id else self.current_deployment
        )
        return deployment.state

    def review_results(self, deployment_id: int = 0) -> None:
        """
        Prepare review information showing test results and differences between environments.

        Args:
            deployment_id: The ID of the deployment

        Raises:
            ValueError: If deployment is not in TESTS_RUN state
        """
        deployment = self.deployment_db.get_deployment(
            deployment_id=deployment_id or self.current_deployment
        )
        print(f"Test results with errors: {deployment.test_results}")
        print("================================")
        print("Deployment payload:")
        pprint(deployment.deployment_payload, indent=2)
        return None

    def approve_deployment(self, deployment_id: int = 0) -> None:
        """
        Approve the deployment for execution.

        Args:
            deployment_id: The ID of the deployment

        Raises:
            ValueError: If deployment is not in REVIEW state or if tests failed
        """
        deployment = self.deployment_db.get_deployment(
            deployment_id=deployment_id or self.current_deployment
        )
        if (
            DeploymentState[deployment.state] != DeploymentState.TESTS_RUN
        ):
            raise ValueError(
                f"Deployment failure => must run tests before approval: {deployment.state}"
            )


        self.deployment_db.update_deployment_state(
            deployment_id=deployment_id or self.current_deployment,
            state=DeploymentState.APPROVED,
        )
        return

    def execute_deployment(self, deployment_id: int = 0) -> None:
        """
        Execute the approved deployment, transferring configurations from source to target.

        Args:
            deployment_id: The ID of the deployment

        Raises:
            ValueError: If deployment is not in APPROVED state
        """
        deployment = self.deployment_db.get_deployment(
            deployment_id=deployment_id or self.current_deployment
        )
        if (
            DeploymentState[deployment.state] != DeploymentState.APPROVED
            or DeploymentState[deployment.state] == DeploymentState.DEPLOYED
            or DeploymentState[deployment.state] == DeploymentState.INITIAL
        ):
            raise ValueError(
                f"Deployment failure => cannot execute deployment in state: {deployment.state}"
            )

        try:
            self.target_db.bulk_insert_config_entries(deployment.deployment_payload)
        except Exception as e:
            _error = f"Deployment failure => error transferring configurations: {e}"
            self.errors.append(_error)
            self.deployment_db.update_deployment_state(
                deployment_id=deployment_id or self.current_deployment,
                state=DeploymentState.DEPLOYMENT_FAILED,
            )
            raise Exception(_error)

        self.deployment_db.update_deployment_state(
            deployment_id=deployment_id or self.current_deployment,
            state=DeploymentState.DEPLOYED,
        )

        return
