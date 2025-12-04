"""SAP Agent with Direct Python Tools for OData Queries.

This agent provides SAP OData integration using direct Python functions,
making it compatible with Agent Engine deployment.

Supports both local development and Agent Engine deployment environments.
"""

import os
import json
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, List

# Enable nested event loops for Agent Engine compatibility
try:
    import nest_asyncio
    nest_asyncio.apply()
except ImportError:
    pass  # nest_asyncio not available, may fail in nested async contexts

# Import Google Secret Manager (lazy loading to avoid startup issues)
HAS_SECRET_MANAGER = False
secretmanager = None

def _get_secret_manager():
    """Lazy load secret manager to avoid import-time permission issues."""
    global secretmanager, HAS_SECRET_MANAGER
    if secretmanager is None:
        try:
            from google.cloud import secretmanager as sm
            secretmanager = sm
            HAS_SECRET_MANAGER = True
        except ImportError:
            HAS_SECRET_MANAGER = False
    return secretmanager

from google.adk.agents.llm_agent import Agent


# =============================================================================
# Secret Management
# =============================================================================

def load_secrets_from_manager(force: bool = False) -> bool:
    """Load SAP credentials from Secret Manager if not in environment.

    Args:
        force: If True, reload secrets even if SAP_HOST is already set

    Returns:
        True if secrets were loaded successfully, False otherwise
    """
    # Only attempt if not already set
    if not force and os.getenv("SAP_HOST"):
        return True

    # Get secret manager (lazy load)
    sm = _get_secret_manager()
    if sm is None:
        print("Debug: Secret Manager not available.")
        return False

    project_id = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("PROJECT_ID")
    if not project_id:
        # Try to get project ID from metadata server (Agent Engine)
        try:
            import urllib.request
            req = urllib.request.Request(
                "http://metadata.google.internal/computeMetadata/v1/project/project-id",
                headers={"Metadata-Flavor": "Google"}
            )
            with urllib.request.urlopen(req, timeout=2) as response:
                project_id = response.read().decode()
                os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
        except Exception:
            pass

    if not project_id:
        print("Debug: PROJECT_ID not found in environment for Secret Manager.")
        return False

    print(f"Debug: Attempting to load secrets for project_id: {project_id}")
    try:
        client = sm.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/sap-credentials/versions/latest"
        response = client.access_secret_version(request={"name": name})
        payload = response.payload.data.decode("UTF-8")
        secrets = json.loads(payload)

        print(f"Debug: Loaded secrets: {list(secrets.keys())}")
        # Set environment variables
        for key, value in secrets.items():
            env_key = f"SAP_{key.upper()}"
            os.environ[env_key] = str(value)

        print("Successfully loaded SAP credentials from Secret Manager.")
        return True
    except Exception as e:
        print(f"Warning: Failed to load secrets from Secret Manager: {e}")
        return False


def ensure_sap_config():
    """Ensure SAP configuration is available. Call this before any SAP operation."""
    print(f"Debug ensure_sap_config: SAP_HOST={os.getenv('SAP_HOST')}, "
          f"PROJECT_ID={os.getenv('GOOGLE_CLOUD_PROJECT')}")

    # Try to load secrets if not already loaded (from env_vars or Secret Manager)
    if not os.getenv("SAP_HOST"):
        try:
            success = load_secrets_from_manager()
            print(f"Debug: load_secrets_from_manager returned {success}")
        except Exception as e:
            print(f"Warning: Could not load from Secret Manager: {e}")
        print(f"Debug: After loading - SAP_HOST={os.getenv('SAP_HOST')}")

    # Reset cached config to pick up new environment variables
    from sap_agent.sap_gw_connector.config import settings
    settings.config = None

    # Verify env vars are set
    required = ["SAP_HOST", "SAP_USERNAME", "SAP_PASSWORD"]
    missing = [v for v in required if not os.getenv(v)]
    if missing:
        raise RuntimeError(f"Missing SAP environment variables: {missing}. "
                          f"Ensure credentials are set via env_vars or Secret Manager.")


def configure_services_path():
    """Configure SAP services path for remote environment."""
    # If explicitly set, respect it
    if os.getenv("SAP_SERVICES_CONFIG_PATH"):
        return

    # Check for services.yaml in the uploaded agent_config directory
    # agent_config should be in the root of the working directory in Agent Engine
    root_dir = Path.cwd()
    services_yaml = root_dir / "agent_config" / "services.yaml"

    if services_yaml.exists():
        os.environ["SAP_SERVICES_CONFIG_PATH"] = str(services_yaml.resolve())
        print(f"Configured SAP services path: {services_yaml}")
    else:
        # Fallback: check relative to this file (for local dev)
        local_yaml = Path(__file__).parent / "services.yaml"
        if local_yaml.exists():
             os.environ["SAP_SERVICES_CONFIG_PATH"] = str(local_yaml.resolve())
             print(f"Configured SAP services path (local): {local_yaml}")
        else:
             print(f"Warning: services.yaml not found in {services_yaml} or {local_yaml}")


# Attempt to load secrets and config at startup
# Only try Secret Manager if SAP_HOST is not already set via env_vars
# This prevents permission errors during Agent Engine startup when env_vars are used
if not os.getenv("SAP_HOST"):
    # Silently try to load - don't crash if it fails
    try:
        load_secrets_from_manager()
    except Exception as e:
        print(f"Note: Could not load from Secret Manager (may use env_vars instead): {e}")
else:
    print(f"SAP credentials already configured via environment variables")
configure_services_path()


# =============================================================================
# Configuration
# =============================================================================

def get_model_name() -> str:
    """Get the LLM model name.

    Can be overridden via SAP_AGENT_MODEL environment variable.
    """
    return os.getenv("SAP_AGENT_MODEL", "gemini-2.5-pro")


MODEL_NAME = get_model_name()


# =============================================================================
# SAP Client Utilities (Lazy Loading)
# =============================================================================

_sap_client_instance = None
_sap_client_lock = asyncio.Lock()


def get_services_config_path() -> Optional[Path]:
    """Get services configuration file path."""
    # Check environment variable first
    env_path = os.getenv("SAP_SERVICES_CONFIG_PATH")
    if env_path:
        return Path(env_path)

    # Check local path
    local_yaml = Path(__file__).parent / "services.yaml"
    if local_yaml.exists():
        return local_yaml

    # Check agent_config path (for Agent Engine)
    agent_config_yaml = Path.cwd() / "agent_config" / "services.yaml"
    if agent_config_yaml.exists():
        return agent_config_yaml

    return None


def _transform_response(data: Dict[str, Any], output_format: str = "json_compact") -> Dict[str, Any]:
    """Transform OData response based on requested format.

    Args:
        data: Raw OData response
        output_format: 'json' for raw response, 'json_compact' for cleaned response

    Returns:
        Transformed response with reduced token usage for json_compact format
    """
    if output_format == "json":
        return data

    # json_compact: Remove __metadata and __deferred navigation links
    results = data.get("d", {}).get("results", [])

    if not results:
        # Handle single entity response (no results array)
        if "d" in data and isinstance(data["d"], dict):
            entity = data["d"]
            clean_entity = {}
            for key, value in entity.items():
                # Skip metadata
                if key == "__metadata":
                    continue
                # Skip deferred navigation links
                if isinstance(value, dict) and "__deferred" in value:
                    continue
                clean_entity[key] = value
            return {"result": clean_entity}
        return data

    # Process results array
    clean_results: List[Dict[str, Any]] = []
    for item in results:
        clean_item: Dict[str, Any] = {}
        for key, value in item.items():
            # Skip metadata
            if key == "__metadata":
                continue
            # Skip deferred navigation links
            if isinstance(value, dict) and "__deferred" in value:
                continue
            # Keep expanded navigation properties (they have actual data)
            clean_item[key] = value
        clean_results.append(clean_item)

    return {"results": clean_results, "count": len(clean_results)}


# =============================================================================
# SAP Tools as Python Functions
# =============================================================================

def sap_list_services() -> Dict[str, Any]:
    """List all available SAP OData services configured in services.yaml.

    Returns:
        Dictionary containing:
        - success: Boolean indicating operation success
        - count: Number of services found
        - services: List of service configurations with id, name, path, version, description, and entities
        - source: Configuration source identifier
    """
    try:
        from sap_agent.sap_gw_connector.config.loader import get_services_config

        config_path = get_services_config_path()
        services_config = get_services_config(config_path)

        # Build service list with details
        services = []
        for service in services_config.services:
            services.append(
                {
                    "id": service.id,
                    "name": service.name,
                    "path": service.path,
                    "version": service.version,
                    "description": service.description,
                    "entities": [
                        {
                            "name": entity.name,
                            "key_field": entity.key_field,
                            "description": entity.description,
                        }
                        for entity in service.entities
                    ],
                }
            )

        return {
            "success": True,
            "count": len(services),
            "services": services,
            "source": "services.yaml configuration",
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


def sap_query(
    service: str,
    entity_set: str,
    filter: Optional[str] = None,
    select: Optional[str] = None,
    top: Optional[int] = None,
    skip: Optional[int] = None,
    format: str = "json_compact"
) -> Dict[str, Any]:
    """Query SAP OData service entity sets with optional filters.

    Args:
        service: OData service name (e.g., 'sales_order')
        entity_set: Entity set name to query (e.g., 'zsd004Set')
        filter: OData filter expression (optional, e.g., "Status eq 'OPEN'")
        select: Comma-separated list of fields to select (optional)
        top: Maximum number of records to return (optional)
        skip: Number of records to skip for pagination (optional)
        format: Output format - 'json' for raw OData response, 'json_compact' removes metadata (default)

    Returns:
        Dictionary containing query results with 'results' array and 'count',
        or error information if the query fails
    """
    try:
        # Ensure SAP credentials are loaded from Secret Manager
        ensure_sap_config()

        from sap_agent.sap_gw_connector.config.settings import get_config
        from sap_agent.sap_gw_connector.config.loader import get_services_config
        from sap_agent.sap_gw_connector.core.sap_client import SAPClient

        # Get SAP connection configuration
        config = get_config(require_sap=True)
        sap_config = config.sap

        config_path = get_services_config_path()
        services_config = get_services_config(config_path)

        # Find service path
        service_info = services_config.get_service(service)
        if not service_info:
            available = services_config.list_service_ids()
            return {
                "success": False,
                "error": f"Service '{service}' not found. Available: {', '.join(available)}"
            }
        service_path = service_info.path

        # Build query parameters
        filters = {"$filter": filter} if filter else None
        select_fields = select.split(",") if select else None

        # Execute query using async wrapper
        async def _execute_query():
            async with SAPClient(config=sap_config) as client:
                result = await client.query_entity_set(
                    service_path=service_path,
                    entity_set=entity_set,
                    filters=filters,
                    select_fields=select_fields,
                    top=top,
                    skip=skip,
                )
                return result

        # Run async function
        result = asyncio.get_event_loop().run_until_complete(_execute_query())

        # Transform response based on format
        return _transform_response(result, format)

    except Exception as e:
        return {"success": False, "error": str(e)}


def sap_get_entity(
    service: str,
    entity_set: str,
    entity_key: str,
    select: Optional[str] = None
) -> Dict[str, Any]:
    """Retrieve a single entity from SAP OData service by key.

    Args:
        service: OData service name (e.g., 'sales_order')
        entity_set: Entity set name (e.g., 'zsd004Set')
        entity_key: Entity key value (e.g., '91000092' for OrderID)
        select: Comma-separated list of fields to select (optional)

    Returns:
        Dictionary containing:
        - success: Boolean indicating operation success
        - service: Service name used
        - entity_set: Entity set queried
        - entity_key: Key used for lookup
        - data: The entity data if found
        - error: Error message if operation failed
    """
    try:
        # Ensure SAP credentials are loaded from Secret Manager
        ensure_sap_config()

        from sap_agent.sap_gw_connector.config.settings import get_config
        from sap_agent.sap_gw_connector.config.loader import get_services_config
        from sap_agent.sap_gw_connector.core.sap_client import SAPClient

        config = get_config(require_sap=True)

        config_path = get_services_config_path()
        services_config = get_services_config(config_path)

        # Validate service exists
        service_config = services_config.get_service(service)
        if not service_config:
            available_services = services_config.list_service_ids()
            return {
                "success": False,
                "error": f"Service '{service}' not found. Available: {', '.join(available_services)}",
            }

        # Validate entity exists in service
        entity_config = service_config.get_entity(entity_set)
        if not entity_config:
            available_entities = [e.name for e in service_config.entities]
            return {
                "success": False,
                "error": f"Entity set '{entity_set}' not found in service '{service}'. "
                         f"Available: {', '.join(available_entities)}",
            }

        # Use service path from configuration
        service_path = service_config.path

        # Parse select fields if provided
        select_fields = None
        if select:
            select_fields = [f.strip() for f in select.split(",")]

        async def _execute_get():
            async with SAPClient(config.sap) as client:
                # Authenticate first
                auth_success = await client.authenticate()
                if not auth_success:
                    return {"success": False, "error": "Authentication failed"}

                # Get entity by key
                result = await client.get_entity(
                    service_path=service_path,
                    entity_set=entity_set,
                    entity_key=entity_key,
                    select_fields=select_fields,
                )

                return {
                    "success": True,
                    "service": service,
                    "entity_set": entity_set,
                    "entity_key": entity_key,
                    "key_field": entity_config.key_field,
                    "data": result,
                }

        # Run async function
        return asyncio.get_event_loop().run_until_complete(_execute_get())

    except Exception as e:
        return {"success": False, "error": str(e)}


# =============================================================================
# Agent Instruction
# =============================================================================

AGENT_INSTRUCTION = '''You are an SAP integration assistant that helps users query and interact with SAP systems through OData services.

## Your Capabilities
You have access to SAP OData tools that enable integration. Use these tools to:
- Query SAP data via OData services using sap_query
- List available SAP entity sets and services using sap_list_services
- Retrieve specific entities by key using sap_get_entity
- Help users understand SAP entity structures and relationships

## Guidelines
1. When a user asks about SAP data, first identify which OData service or entity they need
2. Use sap_list_services to discover available services and their entities
3. Use sap_query for searching/filtering multiple records
4. Use sap_get_entity for retrieving a specific record by its key
5. Present data in a clear, formatted manner

## Response Format
- Always explain what data you're retrieving before executing queries
- Format response data in readable tables or structured lists
- Summarize key findings after presenting raw data
- Offer follow-up suggestions for related queries

## Error Handling
- If authentication fails, suggest checking SAP credentials
- If a service is not found, use sap_list_services to show available services
- If a query returns no data, suggest alternative filters or entities
'''


# =============================================================================
# Root Agent Definition
# =============================================================================

root_agent = Agent(
    model=MODEL_NAME,
    name='sap_agent',
    description='SAP Gateway integration agent for OData queries and operations',
    instruction=AGENT_INSTRUCTION,
    tools=[
        sap_list_services,
        sap_query,
        sap_get_entity,
    ],
)


# =============================================================================
# Utility Functions for Deployment
# =============================================================================

def get_agent_config() -> dict:
    """Get current agent configuration for debugging/logging."""
    return {
        "model": MODEL_NAME,
        "tools": ["sap_list_services", "sap_query", "sap_get_entity"],
        "deployment_mode": "direct_functions",
    }


if __name__ == "__main__":
    # Print configuration for debugging
    config = get_agent_config()
    print("SAP Agent Configuration:")
    for key, value in config.items():
        print(f"  {key}: {value}")
