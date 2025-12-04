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
| MCP subprocess 불가 | Direct Python 함수로 전환 |
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

```
agent-adk-sap-mcp/
├── sap_agent/
│   ├── agent.py              # 메인 Agent 정의
│   ├── services.yaml         # SAP 서비스 설정
│   └── sap_mcp_server/
│       ├── config/
│       │   ├── settings.py   # SAP 연결 설정
│       │   ├── loader.py     # YAML 로더
│       │   └── schemas.py    # Pydantic 스키마
│       └── core/
│           └── sap_client.py # SAP HTTP 클라이언트
├── scripts/
│   └── deploy_agent_engine.py
└── docs/
    ├── DEPLOYMENT_GUIDE.md   # 상세 가이드
    └── QUICK_REFERENCE.md    # 이 문서
```

## 디버깅 팁

```bash
# Agent Engine 로그 확인
gcloud logging read "resource.type=aiplatform.googleapis.com/ReasoningEngine" --limit=50

# Secret 값 확인
gcloud secrets versions access latest --secret=sap-credentials
```
