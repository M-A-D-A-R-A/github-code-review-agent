# PR Code Review Agent (FastAPI · Celery · Postgres · Redis · Agno + Ollama)

An autonomous code-review service for GitHub pull requests.  
It fetches PR diffs, runs lightweight static checks, asks a **local LLM (Ollama) via Agno** to produce a **strict JSON** review, stores results in **Postgres**, and exposes a **FastAPI** API. Work is executed asynchronously using **Celery** with **Redis** as broker/result backend.

---

##  Features

- **API**  
  - `POST /analyze-pr` → enqueue a PR review  
  - `GET /status/{task_id}` → check status  
  - `GET /results/{task_id}` → fetch structured JSON results
- **Async processing** with Celery + Redis
- **Persistent results** in Postgres (JSONB)
- **Local LLM** review via Agno + Ollama (e.g., `llama3.1`, `qwen2.5`)
- **Structured logging** for debugging & metrics

---

##  Tech

- **[FastAPI](https://fastapi.tiangolo.com/)** – lightning-fast web framework
- **[Agno](https://github.com/agnohq/agno)** – agent framework to orchestrate LLMs
- **[uv](https://docs.astral.sh/uv/)** – ultra-fast Python package manager & virtualenvs
- **[Ollama](https://ollama.com/)** – local LLM runtime (pull models like `llama3.1`)
- **[Postgres](https://www.postgresql.org/)** – relational DB (we store results as JSONB)
- **[Celery](https://docs.celeryq.dev/)** + **[Redis](https://redis.io/)** – task queue + broker/backend

---


## Project Layout
```bash
gh-code-review-agent/
    app/
        agents/
            code_reviewer.py 
                 Agno agent for reviewing the PR based on the files using Ollama
        controller/
            github_controller.py 
                controller for the endpoint which exposes all the endpoint
        models/
            db_models.py 
                sqlalchemy db model for  Persistence storage
            schema.py 
                pydantic model for Request/Reponse data parsing, validation, and serialization.
        services/
            github_service.py  
                a service class which fetch the files from github using github apis
            static_checks.py
                service to check the fetch files from github PR for static checks like features, bug etc
        tasks/
            celery_app.py
                celery intilaztation class 
            tasks.py 
                background celery task which performs analysis and stores results based on the task id.
        utils/
            auth_dependancy.py
                auth decorater class which checks if the auth header have verifed JWT for secure API endpoints
            db.py
                sqlalchemy db class which creates tables to the postgrace db based on the models defined in models/db_models.py
        config.py
            config class for fetch env varibles
        main.py
            main class and FastAPu entry point for the endooints and other services.
    etc/ (requirement files)
        base.txt
        dev.txt
Dockerfile
.env.example
.gitignore
pyproject.toml
README.md

```


---

## API

### POST `/github/analyze-pr`
**Body**
```json
{
  "repo_url": "https://github.com/<owner>/<repo>",
  "pr_number": 123,
  "github_token": "optional_token_for_private_repos"
}
```
**Response**
```json
{ "task_id": "uuid", "status": "pending" }
```

### GET `github/status/{task-id}` 
```json
{ "task_id": "uuid", "status": "pending|processing|completed|failed", "error": null }

```

### GET `github/results/{task-id}` 
```json
{
  "task_id": "uuid",
  "status": "completed",
  "results": {
    "files": [
      {
        "name": "main.py",
        "issues": [
          {
            "type": "style",
            "line": 15,
            "description": "Line too long",
            "suggestion": "Break line into multiple lines",
            "severity": "low"
          }
        ]
      }
    ],
    "summary": { "total_files": 1, "total_issues": 1, "critical_issues": 0 }
  }
}
```

### Local Setup (uv · Redis · Ollama · Postgres)
- Prereqs
    - Python 3.11+ (3.12 recommended)
    - macOS/Linux/WSL
    - Git 

- install uv
    - macOS/linus
        ```bash 
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.local/bin:$PATH"   # ensure in PATH
        uv --version
        ```

- create venv
    - ```bash 
        uv venv .venv
        source .venv/bin/activate  
        ```

- Install & run Redis
    - macOS (Homebrew)
        ```bash
        brew install redis
        brew services start redis   # or: redis-server
        ```

- Install Ollama, pull the model and run
    - install ollama
        ```bash
        curl -fsSL https://ollama.com/install.sh | sh
        ```
    - Pull a model (one-time):
        ```bash
        ollama pull llama3.1    # or qwen2.5:14b, deepseek-r1, etc.
        ```
    - Run Ollam
        ```bash
        ollama run llama3.1    # or qwen2.5:14b, deepseek-r1, etc.
        ``` 

- Run API & worker
    - API
        ```bash
        uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
        
        ```
        or if already activated the .venv
        ```bash
        uv run fastapi dev     
        ```
    - Worker
        ```bash
        uv run celery -A app.celery_app.celery worker -l INFO
        ```
        or if already activated the .venv
        ```bash
        celery -A app.tasks.celery_app.celery worker -l INFO
        ```


## Security
I have secured all API endpoint with JWT auth token which you need to pass in the auth headers.
Sample token.
```bash
BEARER_SYSTEM_JWT=
```
for testing purponse you can uncomment this line in main.py [#L11](gh-code-review-agent/app/main.py)

```py
# app = FastAPI(title = get_settings().APP_NAME,dependencies=[Depends(token_required)])
app = FastAPI(title = get_settings().APP_NAME)
```