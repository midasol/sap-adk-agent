#!/bin/bash
# =============================================================================
# SAP Agent Deployment Script (Cloud Build - No Local Docker Required)
# =============================================================================
# Usage: ./scripts/deploy.sh [options]
#
# Options:
#   --project-id    GCP Project ID (required if not set in gcloud config)
#   --region        GCP Region (default: us-central1)
#   --build-only    Only build image, don't deploy
#   --deploy-only   Only deploy, skip build (uses existing image)
#   --help          Show this help message

set -e

# =============================================================================
# Configuration
# =============================================================================

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Default values
REGION="${REGION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-sap-agent}"
REPOSITORY="${REPOSITORY:-agent-images}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT:-agent-engine-sa}"
BUILD_ONLY=false
DEPLOY_ONLY=false

# =============================================================================
# Functions
# =============================================================================

log_info() {
    echo -e "${CYAN}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

show_help() {
    echo "SAP Agent Deployment Script (Cloud Build)"
    echo ""
    echo "This script uses Google Cloud Build for all Docker operations."
    echo "No local Docker installation is required."
    echo ""
    echo "Usage: ./scripts/deploy.sh [options]"
    echo ""
    echo "Options:"
    echo "  --project-id ID   GCP Project ID"
    echo "  --region REGION   GCP Region (default: us-central1)"
    echo "  --build-only      Only build and push image, don't deploy"
    echo "  --deploy-only     Only deploy using existing image"
    echo "  --help            Show this help message"
    echo ""
    echo "Environment variables:"
    echo "  PROJECT_ID        GCP Project ID"
    echo "  REGION            GCP Region"
    echo "  SERVICE_NAME      Cloud Run service name"
    echo "  REPOSITORY        Artifact Registry repository name"
    echo "  SERVICE_ACCOUNT   Service account name"
    echo ""
    echo "Examples:"
    echo "  ./scripts/deploy.sh                    # Full deployment"
    echo "  ./scripts/deploy.sh --build-only      # Build image only"
    echo "  ./scripts/deploy.sh --deploy-only     # Deploy existing image"
    exit 0
}

check_prerequisites() {
    log_info "Checking prerequisites..."

    # Check gcloud
    if ! command -v gcloud &> /dev/null; then
        log_error "gcloud CLI is not installed. Please install it first."
    fi

    # Check project ID
    if [ -z "$PROJECT_ID" ]; then
        PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
        if [ -z "$PROJECT_ID" ]; then
            log_error "PROJECT_ID is not set. Use --project-id or set it in gcloud config."
        fi
    fi

    log_success "Prerequisites check passed!"
    echo "  Project ID: $PROJECT_ID"
    echo "  Region: $REGION"
    echo "  Service: $SERVICE_NAME"
}

setup_gcp() {
    log_info "Setting up GCP resources..."

    # Enable APIs
    log_info "Enabling required APIs..."
    gcloud services enable \
        aiplatform.googleapis.com \
        run.googleapis.com \
        cloudbuild.googleapis.com \
        secretmanager.googleapis.com \
        artifactregistry.googleapis.com \
        --quiet

    # Create service account if not exists
    log_info "Creating service account..."
    gcloud iam service-accounts create $SERVICE_ACCOUNT \
        --display-name="Agent Engine Service Account" \
        2>/dev/null || log_warning "Service account already exists"

    # Grant permissions
    log_info "Granting permissions..."
    for role in "roles/aiplatform.user" "roles/secretmanager.secretAccessor" "roles/logging.logWriter"; do
        gcloud projects add-iam-policy-binding $PROJECT_ID \
            --member="serviceAccount:${SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com" \
            --role="$role" \
            --condition=None \
            --quiet 2>/dev/null || true
    done

    log_success "GCP setup complete!"
}

check_secrets() {
    log_info "Checking secrets..."

    if ! gcloud secrets describe sap-credentials --quiet 2>/dev/null; then
        log_error "Secret 'sap-credentials' not found. Please create it first using 'make secrets-create'"
    fi

    log_success "Secrets verified!"
}

build_with_cloud_build() {
    log_info "Building Docker image with Cloud Build..."
    log_info "This runs entirely in the cloud - no local Docker required."

    IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${SERVICE_NAME}"

    gcloud builds submit \
        --config=agent_engine/cloudbuild-build-only.yaml \
        --substitutions=_REGION=${REGION},_REPOSITORY=${REPOSITORY},_SERVICE_NAME=${SERVICE_NAME} \
        .

    log_success "Docker image built and pushed to: ${IMAGE_URI}:latest"
}

deploy_with_cloud_build() {
    log_info "Deploying to Cloud Run with Cloud Build..."

    gcloud builds submit \
        --config=agent_engine/cloudbuild.yaml \
        --substitutions=_REGION=${REGION},_REPOSITORY=${REPOSITORY},_SERVICE_NAME=${SERVICE_NAME},_SERVICE_ACCOUNT=${SERVICE_ACCOUNT} \
        .

    log_success "Deployment complete!"
}

deploy_service_only() {
    log_info "Deploying to Cloud Run using existing image..."

    IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${SERVICE_NAME}"

    gcloud run deploy $SERVICE_NAME \
        --image="${IMAGE_URI}:latest" \
        --region=$REGION \
        --platform=managed \
        --service-account="${SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com" \
        --cpu=2 \
        --memory=4Gi \
        --min-instances=1 \
        --max-instances=10 \
        --timeout=300 \
        --concurrency=80 \
  --execution-environment=gen2 \
  --set-secrets=SAP_HOST=sap-credentials:host,SAP_PORT=sap-credentials:port,SAP_CLIENT=sap-credentials:client,SAP_USERNAME=sap-credentials:username,SAP_PASSWORD=sap-credentials:password \
  --set-env-vars=SAP_VERIFY_SSL=true,SAP_MCP_SERVER_PATH=sap-mcp-server-stdio,SAP_MCP_CWD=/app/sap-mcp-server,SAP_MCP_TIMEOUT=30.0,SAP_AGENT_MODEL=gemini-3-pro-preview,LOG_LEVEL=INFO,STRUCTURED_LOGGING=true \
  --allow-unauthenticated

echo "Deployment complete!"
}

verify_deployment() {
    log_info "Verifying deployment..."

    # Wait for deployment to stabilize
    sleep 10

    SERVICE_URL=$(gcloud run services describe $SERVICE_NAME \
        --region=$REGION \
        --format='value(status.url)')

    echo ""
    log_success "Service deployed successfully!"
    echo ""
    echo "  Service URL: $SERVICE_URL"
    echo ""

    # Health check
    log_info "Running health check..."
    HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${SERVICE_URL}/health" || echo "000")

    if [ "$HTTP_STATUS" = "200" ]; then
        log_success "Health check passed!"
    else
        log_warning "Health check returned status $HTTP_STATUS"
    fi
}

# =============================================================================
# Main
# =============================================================================

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --project-id)
            PROJECT_ID="$2"
            shift 2
            ;;
        --region)
            REGION="$2"
            shift 2
            ;;
        --build-only)
            BUILD_ONLY=true
            shift
            ;;
        --deploy-only)
            DEPLOY_ONLY=true
            shift
            ;;
        --help)
            show_help
            ;;
        *)
            log_error "Unknown option: $1"
            ;;
    esac
done

# Main execution
echo ""
echo "=============================================="
echo "  SAP Agent Deployment (Cloud Build)"
echo "=============================================="
echo ""
echo "  No local Docker required!"
echo "  All builds run in Google Cloud Build."
echo ""

check_prerequisites

if [ "$BUILD_ONLY" = true ]; then
    log_info "Build-only mode selected"
    setup_gcp
    build_with_cloud_build
    echo ""
    echo "=============================================="
    echo "  Build Complete!"
    echo "=============================================="
    echo ""
    echo "  To deploy, run: ./scripts/deploy.sh --deploy-only"
    echo ""
    exit 0
fi

if [ "$DEPLOY_ONLY" = true ]; then
    log_info "Deploy-only mode selected"
    check_secrets
    deploy_service_only
    verify_deployment
    echo ""
    echo "=============================================="
    echo "  Deployment Complete!"
    echo "=============================================="
    echo ""
    exit 0
fi

# Full deployment
setup_gcp
check_secrets
deploy_with_cloud_build
verify_deployment

echo ""
echo "=============================================="
echo "  Full Deployment Complete!"
echo "=============================================="
echo ""
