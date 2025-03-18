import pytest
from unittest.mock import patch

from backend.deployment_api import DeploymentManager
from backend.models import DeploymentRequest, DeploymentState
from backend.db import ConfigDB


def test_transaction_rollback_on_failure():
    src_db = ConfigDB("test_dev.ddb", env_name="dev")
    tgt_db = ConfigDB("test_prod.ddb", env_name="prod")

    src_db.insert_config_entry("test_key_1", "test_value_1")
    src_db.insert_config_entry("test_key_2", "test_value_2")

    dm = DeploymentManager(source_db=src_db, target_db=tgt_db)

    request = DeploymentRequest(
        source_environment="dev",
        target_environment="prod",
        requested_configs=["test_key_1", "test_key_2"],
    )

    dm.create_deployment(request)
    dm.select_changes(deployment_id=dm.current_deployment, request=request)
    dm.run_tests()
    dm.approve_deployment()

    # target_db.bulk_insert_config_entries to fail halfway through
    with patch.object(
        tgt_db,
        "bulk_insert_config_entries",
        side_effect=Exception("Simulated DB failure"),
    ):
        # has to raise exception but should also rollback any changes
        with pytest.raises(Exception):
            dm.execute_deployment()

    # check deployment state is DEPLOYMENT_FAILED
    assert dm.get_current_state() == DeploymentState.DEPLOYMENT_FAILED.name

    # check target DB hasn't changed
    target_configs = tgt_db.get_all_configs()
    assert len(target_configs) == 0


def test_invalid_state_transitions():
    src_db = ConfigDB("test_dev.ddb", env_name="dev")
    tgt_db = ConfigDB("test_prod.ddb", env_name="prod")

    src_db.insert_config_entry("key1", "value1")
    src_db.insert_config_entry("key2", "value2")

    dm = DeploymentManager(source_db=src_db, target_db=tgt_db)

    request = DeploymentRequest(
        source_environment="dev",
        target_environment="prod",
        requested_configs=["key1", "key2"],
    )

    dm.create_deployment(request)

    # can we skip directly to execution (INITIAL -> DEPLOYED)?
    with pytest.raises(ValueError, match="cannot execute deployment in state: INITIAL"):
        dm.execute_deployment()

    # can we approve before tests are run (!TESTS_RUN -> APPROVED)??
    with pytest.raises(ValueError, match="must run tests before approval"):
        dm.approve_deployment()

    dm.select_changes(deployment_id=dm.current_deployment, request=request)

    # can I execute deployment before tests and approval?
    with pytest.raises(
        ValueError, match="cannot execute deployment in state: CHANGES_SELECTED"
    ):
        dm.execute_deployment()


def test_non_existent_config_keys():
    src_db = ConfigDB("test_dev.ddb", env_name="dev")
    tgt_db = ConfigDB("test_prod.ddb", env_name="prod")

    src_db.insert_config_entry("existing_key", "value")

    dm = DeploymentManager(source_db=src_db, target_db=tgt_db)

    # deployment request with one existing and one non-existent key
    request = DeploymentRequest(
        source_environment="dev",
        target_environment="prod",
        requested_configs=["existing_key", "non_existent_key"],
    )

    dm.create_deployment(request)

    # should either raise an exception or handle the missing key
    try:
        dm.select_changes(deployment_id=dm.current_deployment, request=request)
        deployment = dm.deployment_db.get_deployment(dm.current_deployment)
        assert len(deployment.deployment_payload) == 1
        assert deployment.deployment_payload[0]["config_key"] == "existing_key"
    except ValueError as e:
        assert "no changes found" in str(e) or "missing keys" in str(e)
