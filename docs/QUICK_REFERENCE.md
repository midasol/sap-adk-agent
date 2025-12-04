# SAP Agent 빠른 참조 가이드

## 배포 명령어

```bash
# 배포 실행
python scripts/deploy_agent_engine.py

# 배포 확인
gcloud ai reasoning-engines list --region=us-central1
```

## 핵심 설정

| 항목 | 값 |
|------|-----|
| SAP Host (내부) | `10.142.0.5` |
| SAP Port | `44300` |
| Model | `gemini-2.5-pro` |
| Region | `us-central1` |

## 주요 이슈 해결 요약

| 이슈 | 해결 |
|------|------|
| Gateway subprocess 불가 | Direct Python 함수로 전환 |
| serviceUsageConsumer 권한 | 서비스 계정에 역할 부여 |
| Secret Manager import 오류 | Lazy loading 패턴 적용 |
| Event loop 충돌 | `nest_asyncio` 추가 |
| SAP 연결 타임아웃 | 내부 IP로 변경 |

## Secret Manager 업데이트

```bash
echo '{
  "host": "10.142.0.5",
  "port": 44300,
  "client": "100",
  "username": "USERNAME",
  "password": "PASSWORD"
}' | gcloud secrets versions add sap-credentials --data-file=-
```

## 권한 부여

```bash
PROJECT_ID="sap-advanced-workshop-gck"
PROJECT_NUMBER="110191959938"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-aiplatform-re.iam.gserviceaccount.com" \
  --role="roles/serviceusage.serviceUsageConsumer"
```

## Agent 테스트

```python
from vertexai import agent_engines

agent = agent_engines.get("projects/110191959938/locations/us-central1/reasoningEngines/5675639440161112064")
session = agent.create_session()
response = session.send_message("SAP 서비스 목록 보여줘")
```

## 파일 구조

```mermaid
flowchart LR
    subgraph Root["📁 agent-adk-sap-gw/"]
        subgraph SapAgent["📁 sap_agent/"]
            AgentPy["🤖 agent.py"]
            ServicesYaml["⚙️ services.yaml"]

            subgraph GWConnector["📁 sap_gw_connector/"]
                subgraph Config["📁 config/"]
                    Settings["settings.py"]
                    Loader["loader.py"]
                    Schemas["schemas.py"]
                end
                subgraph Core["📁 core/"]
                    SAPClient["sap_client.py"]
                end
            end
        end

        subgraph Scripts["📁 scripts/"]
            Deploy["deploy_agent_engine.py"]
        end

        subgraph Docs["📁 docs/"]
            Guide["DEPLOYMENT_GUIDE.md"]
            Quick["QUICK_REFERENCE.md"]
        end
    end

    style SapAgent fill:#e3f2fd,stroke:#1976d2
    style GWConnector fill:#e8f5e9,stroke:#388e3c
    style Scripts fill:#fff3e0,stroke:#f57c00
    style Docs fill:#fce4ec,stroke:#c2185b
```

## 디버깅 팁

```bash
# Agent Engine 로그 확인
gcloud logging read "resource.type=aiplatform.googleapis.com/ReasoningEngine" --limit=50

# Secret 값 확인
gcloud secrets versions access latest --secret=sap-credentials
```
