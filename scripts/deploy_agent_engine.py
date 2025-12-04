"""Deploy SAP Agent to Vertex AI Agent Engine.

This script deploys the SAP Agent with direct Python function tools
(not MCP subprocess) for Agent Engine compatibility.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Ensure PROJECT_ID is set in os.environ for Secret Manager access
PROJECT_ID = os.getenv("PROJECT_ID", "sap-advanced-workshop-gck")
os.environ["PROJECT_ID"] = PROJECT_ID
os.environ["GOOGLE_CLOUD_PROJECT"] = PROJECT_ID  # For consistency

from vertexai import agent_engines
import vertexai
import sap_agent.agent

# Load SAP credentials from .env.server (for local testing before deploy)
env_path = Path("sap-mcp-server/.env.server")
if env_path.exists():
    print(f"Loading environment variables from {env_path}")
    load_dotenv(dotenv_path=env_path)
else:
    print(f"Warning: {env_path} not found. Ensure environment variables are set.")

# Configuration
LOCATION = os.getenv("REGION", "us-central1")
STAGING_BUCKET = os.getenv("STAGING_BUCKET", "gs://sap-advanced-workshop-gck_cloudbuild")
NETWORK_ATTACHMENT = f"projects/{PROJECT_ID}/regions/{LOCATION}/networkAttachments/agent-engine-attachment"

print(f"Initializing Vertex AI SDK...")
print(f"Project: {PROJECT_ID}")
print(f"Location: {LOCATION}")
print(f"Staging Bucket: {STAGING_BUCKET}")
print(f"Network Attachment: {NETWORK_ATTACHMENT}")

vertexai.init(
    project=PROJECT_ID,
    location=LOCATION,
    staging_bucket=STAGING_BUCKET,
)

print("Preparing agent for deployment...")

# Use the root_agent directly from sap_agent.agent module
# The agent now uses direct Python function tools instead of MCP subprocess,
# making it compatible with Agent Engine's serverless environment.
print(f"Agent Model: {sap_agent.agent.MODEL_NAME}")
print(f"Agent Tools: {[tool.__name__ for tool in sap_agent.agent.root_agent.tools]}")

# Wrap the agent in an AdkApp object
app = agent_engines.AdkApp(
    agent=sap_agent.agent.root_agent,
    enable_tracing=True,
)

print("Deploying to Agent Engine...")

# Service account with Secret Manager access
SERVICE_ACCOUNT = f"agent-engine-sa@{PROJECT_ID}.iam.gserviceaccount.com"
print(f"Service Account: {SERVICE_ACCOUNT}")

# Get SAP credentials from Secret Manager for env_vars
from google.cloud import secretmanager
import json

def get_sap_credentials():
    """Load SAP credentials from Secret Manager."""
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{PROJECT_ID}/secrets/sap-credentials/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return json.loads(response.payload.data.decode("UTF-8"))

print("Loading SAP credentials from Secret Manager...")
sap_creds = get_sap_credentials()
print(f"Loaded credentials: {list(sap_creds.keys())}")

# Pass SAP credentials as environment variables
# Note: GOOGLE_CLOUD_PROJECT is set automatically by Agent Engine
env_vars = {
    "SAP_HOST": sap_creds.get("host", ""),
    "SAP_PORT": str(sap_creds.get("port", "44300")),
    "SAP_CLIENT": sap_creds.get("client", "100"),
    "SAP_USERNAME": sap_creds.get("username", ""),
    "SAP_PASSWORD": sap_creds.get("password", ""),
}

try:
    remote_app = agent_engines.create(
        agent_engine=app,
        requirements=[
            "google-cloud-aiplatform[adk,agent_engines]>=1.128.0",
            "google-adk>=1.15.0",
            "google-cloud-secret-manager>=2.16.0",
            "pydantic>=2.5.0",
            "pydantic-settings>=2.1.0",
            "aiohttp>=3.9.0",
            "asyncio-throttle>=1.0.2",
            "structlog>=23.2.0",
            "tenacity>=8.2.3",
            "cryptography>=41.0.7",
            "xmltodict>=0.13.0",
            "pyyaml>=6.0.1",
            "python-dotenv>=1.0.0",
            "nest-asyncio>=1.5.0",
        ],
        # Include sap_agent package in the deployment
        extra_packages=["./sap_agent"],
        display_name="SAP Agent",
        # Service account with proper permissions
        service_account=SERVICE_ACCOUNT,
        # Pass SAP credentials as environment variables
        env_vars=env_vars,
        # Configure PSC Interface for private connectivity
        psc_interface_config={
            "network_attachment": NETWORK_ATTACHMENT,
        }
    )

    print(f"Deployment finished!")
    print(f"Resource Name: {remote_app.resource_name}")
except Exception as e:
    print(f"Deployment failed: {e}")
