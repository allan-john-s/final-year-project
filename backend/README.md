# Backend

FastAPI application (Python 3.12) for the Accessibility Remediation Framework,
organized in layers: `api` → `services` → `repositories`.

## Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in values
```

## Run

```bash
uvicorn app.main:app --reload   # http://localhost:8000
```

Interactive docs: http://localhost:8000/docs

## Test

```bash
pytest
```

## Endpoints

| Method | Path      | Purpose                          |
| ------ | --------- | -------------------------------- |
| GET    | `/`       | Service metadata                 |
| GET    | `/health` | Liveness probe (for orchestration) |

## Structure

```
app/
├── api/          # routers & handlers
├── core/         # settings, logging, app factory
├── middleware/   # HTTP middleware
├── services/     # application services
├── repositories/ # data access
├── schemas/      # Pydantic v2 schemas
├── models/       # domain models
├── utils/        # helpers
└── tests/        # test suite
```
