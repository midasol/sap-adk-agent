# ============================================================================
# Step 6: Create Secret for SAP Credentials
# ============================================================================
echo ""
echo "============================================================================"
echo "Step 6: Setting up Secret Manager for SAP Credentials"
echo "============================================================================"

PROJECT_ID="sap-advanced-workshop-gck"
SECRET_NAME="sap-credentials"

if gcloud secrets describe $SECRET_NAME --project=$PROJECT_ID > /dev/null 2>&1; then
    echo ""
    echo "echo '{"
    echo '  "host": "34.75.92.206",'
    echo '  "port": 44300,'
    echo '  "client": "100",'
    echo '  "username": "admin",'
    echo '  "password": "Ahfelqm2@13"'
    echo "}' | gcloud secrets versions add $SECRET_NAME --data-file=-"
    echo ""
else
    gcloud secrets create $SECRET_NAME \
        --project=$PROJECT_ID \
        --replication-policy="automatic"
    echo ""
    echo "echo '{"
    echo '  "host": "34.75.92.206",'
    echo '  "port": 44300,'
    echo '  "client": "100",'
    echo '  "username": "admin",'
    echo '  "password": "Ahfelqm2@13"'
    echo "}' | gcloud secrets versions add $SECRET_NAME --data-file=-"
    echo ""
fi
