#

---

# Configuration Deployment System

A robust Python-based system for managing the deployment of configuration parameters between environments.

## Overview

This system facilitates the controlled migration of configuration key-value pairs from development to production environments. It implements a comprehensive deployment workflow with state tracking, validation testing, and approval processes to ensure safe and reliable configuration changes.

## System Architecture

The system consists of four main components:

- **Database Layer**: Handles interactions with DuckDB databases for both configuration and deployment state management
- **Models Layer**: Defines data structures and state enumerations
- **API Layer**: Provides methods for managing the deployment lifecycle
- **Settings**: Manages environment-specific configurations and defaults


## Features

- **Environment Management**: Supports dev and prod environments with separate configuration databases
- **Deployment State Machine**: Tracks deployments through their lifecycle:
    - Initial
    - Changes Selected
    - Tests Run
    - Review
    - Approved
    - Deployed
    - Deployment Failed (error state)
- **Validation Testing**: Ensures configuration entries are valid before deployment
- **Transaction Safety**: Uses SQLModel/SQLAlchemy sessions for database transaction integrity
- **Timezone Support**: Properly handles timestamps with timezone information


## Installation

### Prerequisites

- Python 3.8+
- DuckDB


### Setup

```bash
# Clone the repository
git clone git@github.com:bmveee/deploybot.git


# or - extract from archive
tar zxvf deploybot-master.tgz

# change directory
cd deploybot

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Database Structure

The system utilizes three DuckDB database files:

1. **Development Configuration**: Stores configuration parameters in the development environment
2. **Production Configuration**: Stores configuration parameters in the production environment
3. **Deployment State**: Tracks deployment metadata and current state

### Database Schema

**Configuration Tables**:

```text
config_key: VARCHAR (Primary Key)
value: VARCHAR
EffectiveDate: TIMESTAMP WITH TIME ZONE
```

**Deployment Table**:

```text
id: INTEGER (Primary Key)
state: VARCHAR
source_env: VARCHAR
target_env: VARCHAR
deployment_payload: JSON
test_results: VARCHAR
created_at: TIMESTAMP
updated_at: TIMESTAMP
```


## Usage

### Basic Workflow

0. Sample dev.ddb is provided with a handful of rows of data

1. **Initiate a new deployment**: from jupyter notebook (test.ipynb)
```python
# Initialize Databases
from backend.db import ConfigDB
from backend.models import DeploymentRequest
from backend.deployment_api import DeploymentManager
src_db = ConfigDB('dev.ddb', env_name='dev')
tgt_db = ConfigDB('prod.ddb', env_name='prod')

# Initialize Deployment Manager
dm = DeploymentManager(source_db=src_db, target_db=tgt_db)

request = DeploymentRequest(
    source_environment='dev',
    target_environment='prod',
    requested_configs= ["key_EhszL_0", "key_ubBJS_9"]
)

# Create first deployment
dm.create_deployment(request)
print(dm.current_deployment, dm.get_current_state())

# Select Changes
dm.select_changes(deployment_id=dm.current_deployment, request=request)
print(dm.current_deployment, dm.get_current_state())

# Run tests
dm.run_tests()
print(dm.current_deployment, dm.get_current_state())

# Approve Deployment
dm.approve_deployment()
print(dm.current_deployment, dm.get_current_state())

# Execute Deploymnet
dm.execute_deployment()
print(dm.current_deployment, dm.get_current_state())

# Tear down connections
src_db.engine.dispose()
tgt_db.engine.dispose()
dm.deployment_db.engine.dispose()

```


## Error Handling

The system implements error handling at multiple levels:

- Validation errors during configuration testing
- Database transaction failures
- State transition errors
- Permission errors for read-only databases

Failed deployments are automatically marked with `DEPLOYMENT_FAILED` state and include detailed error information.

## Development

### Type Checking

This project uses Python type hints throughout. Run static type checking with:

```bash
mypy backend/
```

### Running Tests

A test suite is provided for key functionality and edge cases:

```bash
python -m pytest tests/
```
