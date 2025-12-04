# SAP Agent with Google ADK

SAP Gateway OData 서비스와 통합된 AI Agent로, 자연어를 통해 SAP 데이터를 조회하고 분석할 수 있습니다.

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![Google ADK](https://img.shields.io/badge/Google%20ADK-1.15+-green.svg)](https://cloud.google.com/vertex-ai/docs/reasoning-engine/overview)
[![Vertex AI](https://img.shields.io/badge/Vertex%20AI-Agent%20Engine-orange.svg)](https://cloud.google.com/vertex-ai)

---

## 목차

- [개요](#개요)
- [아키텍처](#아키텍처)
- [프로젝트 구조](#프로젝트-구조)
- [시작하기](#시작하기)
- [사용법](#사용법)
- [배포](#배포)
- [개발 가이드](#개발-가이드)
- [라이선스](#라이선스)

---

## 개요

### 프로젝트 목적

SAP OData 서비스와 통합된 AI Agent를 Google Cloud의 Vertex AI Agent Engine에 배포하여, 자연어로 SAP 데이터를 조회하고 분석할 수 있는 시스템을 제공합니다.

### 주요 기능

| 기능 | 설명 |
|------|------|
| `sap_list_services` | 사용 가능한 SAP OData 서비스 목록 조회 |
| `sap_query` | SAP 엔티티 세트에 대한 필터링 쿼리 실행 |
| `sap_get_entity` | 특정 키로 단일 엔티티 조회 |

### 기술 스택

| 구성요소 | 기술 |
|---------|------|
| AI Framework | Google ADK (Agent Development Kit) |
| LLM Model | Gemini 2.5 Pro |
| 배포 플랫폼 | Vertex AI Agent Engine |
| SAP 연동 | OData v2 Protocol |
| 인증 관리 | Google Secret Manager |
| 네트워크 | Private Service Connect (PSC) |
| HTTP Client | aiohttp (async) |
| 설정 관리 | Pydantic Settings |

---

## 아키텍처

### 시스템 아키텍처

```mermaid
flowchart TB
    subgraph User["사용자"]
        U["👤 User"]
    end

    subgraph GCP["Google Cloud Platform"]
        subgraph AE["Vertex AI Agent Engine"]
            Agent["🤖 SAP Agent<br/>(Google ADK + Gemini)"]
            subgraph Tools["Agent Tools"]
                ListSvc["📋 sap_list_services"]
                Query["🔍 sap_query"]
                GetEntity["📄 sap_get_entity"]
            end
        end

        SM["🔐 Secret Manager<br/>(SAP Credentials)"]
        PSC["🔗 Private Service Connect"]
    end

    subgraph SAP["SAP System"]
        GW["🏢 SAP Gateway"]
        subgraph OData["OData Services"]
            SO["Sales Order"]
            CU["Customer"]
            MA["Material"]
            FL["Flight"]
        end
    end

    U -->|"자연어 질의"| Agent
    Agent --> Tools
    Agent -.->|"env_vars"| SM
    Tools -->|"HTTP/OData"| PSC
    PSC -->|"Private Network"| GW
    GW --> OData
    Agent -->|"자연어 응답"| U
```

### 컴포넌트 다이어그램

```mermaid
classDiagram
    class Agent {
        +MODEL_NAME: str
        +root_agent: Agent
        +sap_list_services() Dict
        +sap_query() Dict
        +sap_get_entity() Dict
        +ensure_sap_config()
        +load_secrets_from_manager()
    }

    class SAPClient {
        -config: SAPConnectionConfig
        -session: aiohttp.ClientSession
        -authenticator: SAPAuthenticator
        +authenticate() bool
        +query_entity_set() Dict
        +get_entity() Dict
        +create_entity() Dict
        +update_entity() Dict
        +delete_entity() bool
    }

    class SAPAuthenticator {
        -config: SAPConnectionConfig
        -current_token: AuthToken
        +get_valid_token() AuthToken
        +invalidate_token()
        +get_auth_headers() Dict
    }

    class AuthToken {
        +csrf_token: str
        +cookies: Dict
        +expires_at: datetime
        +is_expired: bool
        +is_valid: bool
    }

    class SAPConnectionConfig {
        +host: str
        +port: int
        +client: str
        +username: str
        +password: str
        +verify_ssl: bool
        +timeout: int
    }

    class ServicesYAMLConfig {
        +gateway: GatewayConfig
        +services: List~ServiceConfig~
        +get_service() ServiceConfig
        +list_service_ids() List
    }

    Agent --> SAPClient : uses
    SAPClient --> SAPAuthenticator : authenticates via
    SAPAuthenticator --> AuthToken : manages
    SAPClient --> SAPConnectionConfig : configured by
    Agent --> ServicesYAMLConfig : loads
```

### SAP 쿼리 시퀀스 다이어그램

```mermaid
sequenceDiagram
    participant U as 👤 User
    participant A as 🤖 Agent (Gemini)
    participant T as 🔧 sap_query Tool
    participant C as 📡 SAPClient
    participant Auth as 🔐 Authenticator
    participant SAP as 🏢 SAP Gateway

    U->>A: "판매 오더 목록을 보여줘"
    A->>A: Intent Parsing & Tool Selection
    A->>T: sap_query(service="Z_SALES_ORDER_GENAI_SRV", entity_set="zsd004Set")
    T->>T: ensure_sap_config()
    T->>C: query_entity_set()

    rect rgb(200, 220, 240)
        Note over C,SAP: Authentication Flow
        C->>Auth: get_valid_token()
        Auth->>SAP: GET /sap/opu/odata/... (X-CSRF-Token: Fetch)
        SAP-->>Auth: 200 OK + CSRF Token + Cookies
        Auth-->>C: AuthToken
    end

    rect rgb(220, 240, 200)
        Note over C,SAP: Data Query Flow
        C->>SAP: GET /sap/opu/odata/SAP/Z_SALES_ORDER_GENAI_SRV/zsd004Set?$format=json
        SAP-->>C: 200 OK + JSON Response
    end

    C-->>T: {"results": [...], "count": N}
    T-->>A: Formatted Results
    A-->>U: "총 15개의 판매 오더가 있습니다:\n1. 91000092 - ₩1,500,000\n2. ..."
```

### 데이터 플로우

```mermaid
flowchart LR
    subgraph Input["입력"]
        NL["📝 자연어 질의<br/>'판매 오더 목록 보여줘'"]
    end

    subgraph Processing["처리"]
        direction TB
        Agent["🤖 Agent<br/>(Gemini 2.5 Pro)"]
        Tool["🔧 Tool Selection<br/>sap_query"]
        Auth["🔐 Authentication<br/>CSRF Token"]
        OData["📡 OData Request<br/>HTTP GET"]
    end

    subgraph Transform["변환"]
        JSON["📄 JSON Response<br/>{results: [...]}"]
        Clean["🧹 Response Transform<br/>Compact Format"]
    end

    subgraph Output["출력"]
        NLR["💬 자연어 응답<br/>'15개의 판매 오더가...'"]
    end

    NL --> Agent --> Tool --> Auth --> OData --> JSON --> Clean --> NLR
```

---

## 프로젝트 구조

```
agent-adk-sap-mcp/
├── sap_agent/                      # 메인 에이전트 패키지
│   ├── __init__.py
│   ├── agent.py                    # 🤖 Google ADK Agent 정의
│   ├── services.yaml               # ⚙️ SAP OData 서비스 설정
│   └── sap_mcp_server/             # SAP 통신 모듈
│       ├── __init__.py
│       ├── config/                 # 설정 관리
│       │   ├── __init__.py
│       │   ├── settings.py         # Pydantic 설정 클래스
│       │   ├── schemas.py          # YAML 스키마 정의
│       │   └── loader.py           # YAML 로더
│       ├── core/                   # 핵심 기능
│       │   ├── __init__.py
│       │   ├── sap_client.py       # 📡 SAP HTTP 클라이언트
│       │   ├── auth.py             # 🔐 CSRF 인증
│       │   └── exceptions.py       # 예외 정의
│       ├── tools/                  # MCP 도구 클래스
│       │   ├── __init__.py
│       │   ├── base.py             # 기본 도구 클래스
│       │   ├── query_tool.py       # 쿼리 도구
│       │   ├── entity_tool.py      # 엔티티 도구
│       │   ├── service_tool.py     # 서비스 도구
│       │   └── auth_tool.py        # 인증 도구
│       ├── transports/             # 전송 계층
│       │   └── stdio.py            # STDIO 전송
│       ├── protocol/               # 프로토콜 정의
│       │   └── schemas.py
│       └── utils/                  # 유틸리티
│           ├── logger.py
│           └── validators.py
├── scripts/                        # 배포 및 테스트 스크립트
│   ├── deploy_agent_engine.py      # 🚀 Agent Engine 배포
│   ├── deploy.sh                   # 배포 셸 스크립트
│   ├── test_agent_engine.py        # 테스트
│   ├── test_deployed_sap_agent.py
│   ├── test_remote_agent_v2.py
│   └── cleanup_agent_engines.py    # 정리 스크립트
├── docs/                           # 문서
│   ├── DEPLOYMENT_GUIDE.md         # 📚 상세 배포 가이드
│   └── QUICK_REFERENCE.md          # 📋 빠른 참조
├── pyproject.toml                  # 📦 프로젝트 설정
├── .gcloudignore                   # GCloud 제외 파일
└── README.md                       # 이 문서
```

### 주요 파일 설명

| 파일 | 설명 |
|------|------|
| `sap_agent/agent.py` | Google ADK Agent 정의, 3개의 SAP 도구 함수 포함 |
| `sap_agent/services.yaml` | SAP OData 서비스 및 엔티티 설정 |
| `sap_agent/sap_mcp_server/core/sap_client.py` | aiohttp 기반 비동기 SAP HTTP 클라이언트 |
| `sap_agent/sap_mcp_server/core/auth.py` | CSRF 토큰 기반 SAP 인증 처리 |
| `sap_agent/sap_mcp_server/config/settings.py` | Pydantic 기반 환경 설정 관리 |
| `scripts/deploy_agent_engine.py` | Vertex AI Agent Engine 배포 스크립트 |

---

## 시작하기

### 요구사항

- Python 3.11 이상
- Google Cloud SDK
- SAP Gateway 접근 권한
- GCP 프로젝트 (Vertex AI, Secret Manager 활성화)

### 설치

```bash
# 저장소 클론
git clone <repository-url>
cd agent-adk-sap-mcp

# 가상환경 생성 및 활성화
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 의존성 설치
pip install -e ".[dev]"
```

### 환경 설정

#### 1. SAP 자격증명 설정

로컬 개발용 `.env` 파일 생성:

```bash
# sap_agent/.env
SAP_HOST=your-sap-host.com
SAP_PORT=44300
SAP_CLIENT=100
SAP_USERNAME=your_username
SAP_PASSWORD=your_password
```

#### 2. Google Cloud 인증

```bash
# GCP 인증
gcloud auth application-default login

# 프로젝트 설정
gcloud config set project YOUR_PROJECT_ID
```

#### 3. Secret Manager 설정 (배포용)

```bash
# Secret 생성
gcloud secrets create sap-credentials --replication-policy="automatic"

# Secret 값 설정
echo '{
  "host": "10.142.0.5",
  "port": 44300,
  "client": "100",
  "username": "YOUR_USERNAME",
  "password": "YOUR_PASSWORD"
}' | gcloud secrets versions add sap-credentials --data-file=-
```

---

## 사용법

### SAP 서비스 설정

`sap_agent/services.yaml` 파일에서 SAP OData 서비스를 설정합니다:

```yaml
gateway:
  base_url_pattern: "https://{host}:{port}/sap/opu/odata"
  auth_endpoint:
    use_catalog_metadata: true

services:
  - id: Z_SALES_ORDER_GENAI_SRV
    name: "Sales Order GenAI Service"
    path: "/SAP/Z_SALES_ORDER_GENAI_SRV"
    version: v2
    entities:
      - name: zsd004Set
        key_field: Vbeln
        description: "Sales orders entity set"
```

### 로컬 테스트

```python
from sap_agent.agent import root_agent, sap_list_services, sap_query

# 서비스 목록 조회
services = sap_list_services()
print(services)

# 데이터 쿼리
result = sap_query(
    service="Z_SALES_ORDER_GENAI_SRV",
    entity_set="zsd004Set",
    top=10
)
print(result)
```

### Agent Engine 사용

```python
from vertexai import agent_engines

# 배포된 Agent 로드
agent = agent_engines.get("projects/PROJECT_NUMBER/locations/REGION/reasoningEngines/AGENT_ID")

# 세션 생성 및 쿼리
session = agent.create_session()
response = session.send_message("SAP에서 최근 판매 오더 10개를 보여줘")
print(response.text)
```

---

## 배포

### Vertex AI Agent Engine 배포

```bash
# 배포 스크립트 실행
python scripts/deploy_agent_engine.py
```

배포 스크립트는 다음을 수행합니다:
1. Secret Manager에서 SAP 자격증명 로드
2. Agent를 AdkApp으로 래핑
3. PSC 네트워크 설정과 함께 Agent Engine에 배포

### 배포 설정

| 항목 | 값 |
|------|-----|
| Region | us-central1 |
| Model | gemini-2.5-pro |
| Network | PSC (Private Service Connect) |
| Service Account | agent-engine-sa@PROJECT.iam.gserviceaccount.com |

### 배포 확인

```bash
# Agent Engine 목록 확인
gcloud ai reasoning-engines list --region=us-central1
```

자세한 배포 가이드는 [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md)를 참조하세요.

---

## 개발 가이드

### 코드 스타일

```bash
# Ruff 린트 실행
ruff check .

# 타입 체크
mypy sap_agent

# 스펠 체크
codespell
```

### 테스트

```bash
# 테스트 실행
pytest

# 커버리지 포함
pytest --cov=sap_agent
```

### 새 SAP 서비스 추가

1. `services.yaml`에 서비스 정의 추가
2. SAP 트랜잭션 `/IWFND/MAINT_SERVICE`에서 서비스 활성화 확인
3. 로컬에서 테스트 후 배포

---

## 트러블슈팅

### 일반적인 이슈

| 이슈 | 해결 방법 |
|------|----------|
| MCP subprocess 불가 | Direct Python 함수로 전환됨 |
| serviceUsageConsumer 권한 오류 | 서비스 계정에 역할 부여 |
| Secret Manager import 오류 | Lazy loading 패턴 적용됨 |
| Event loop 충돌 | `nest_asyncio` 패키지 사용 |
| SAP 연결 타임아웃 | 내부 IP 확인 (PSC 사용 시) |

자세한 트러블슈팅은 [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md)를 참조하세요.

---

## 라이선스

MIT License

---

## 참고 문서

- [Google ADK Documentation](https://cloud.google.com/vertex-ai/docs/reasoning-engine/overview)
- [Vertex AI Agent Engine](https://cloud.google.com/vertex-ai/docs/reasoning-engine/deploy)
- [SAP OData Services](https://help.sap.com/docs/SAP_NETWEAVER_AS_ABAP_751_IP)
