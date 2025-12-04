#!/bin/bash
set -e

# Configuration
PROJECT_ID="sap-advanced-workshop-gck"
REGION="us-central1" # Agent Engine Region
VPC_NAME="sap-cal-default-network"
PCS_SUBNET_NAME="psc-attachment-subnet"
PCS_SUBNET_RANGE="192.168.10.0/28" # Adjust if overlapping
ATTACHMENT_NAME="agent-engine-attachment"
SAP_IP="10.142.0.5"

echo "Setting project to $PROJECT_ID..."
gcloud config set project $PROJECT_ID

echo "Enabling necessary APIs..."
gcloud services enable compute.googleapis.com aiplatform.googleapis.com

# 1. Check/Create PSC Subnet
if gcloud compute networks subnets describe $PCS_SUBNET_NAME --region=$REGION --project=$PROJECT_ID > /dev/null 2>&1; then
    echo "Subnet $PCS_SUBNET_NAME already exists."
else
    echo "Creating PSC subnet $PCS_SUBNET_NAME..."
    gcloud compute networks subnets create $PCS_SUBNET_NAME \
        --project=$PROJECT_ID \
        --network=$VPC_NAME \
        --range=$PCS_SUBNET_RANGE \
        --region=$REGION
fi

# 2. Check/Create Network Attachment
if gcloud compute network-attachments describe $ATTACHMENT_NAME --region=$REGION --project=$PROJECT_ID > /dev/null 2>&1; then
    echo "Network attachment $ATTACHMENT_NAME already exists."
else
    echo "Creating Network Attachment $ATTACHMENT_NAME..."
    gcloud compute network-attachments create $ATTACHMENT_NAME \
        --project=$PROJECT_ID \
        --region=$REGION \
        --connection-preference=ACCEPT_AUTOMATIC \
        --subnets=$PCS_SUBNET_NAME
fi

# 3. Create Firewall Rule for Agent Engine Access
# Allow traffic from PSC subnet to SAP System
FW_RULE_NAME="allow-agent-engine-to-sap"
if gcloud compute firewall-rules describe $FW_RULE_NAME --project=$PROJECT_ID > /dev/null 2>&1; then
    echo "Firewall rule $FW_RULE_NAME already exists."
else
    echo "Creating firewall rule to allow Agent Engine traffic..."
    gcloud compute firewall-rules create $FW_RULE_NAME \
        --project=$PROJECT_ID \
        --network=$VPC_NAME \
        --action=ALLOW \
        --direction=INGRESS \
        --rules=tcp:44300,tcp:8000,tcp:443,tcp:80 \
        --source-ranges="$PSC_SUBNET_RANGE" \
        --destination-ranges="10.142.0.5/32" \
        --description="Allow Agent Engine PSC traffic to SAP"
fi

echo "Infrastructure setup complete."
echo "Network Attachment: projects/$PROJECT_ID/regions/$REGION/networkAttachments/$ATTACHMENT_NAME"
echo "Please update your deployment script with this Network Attachment."
