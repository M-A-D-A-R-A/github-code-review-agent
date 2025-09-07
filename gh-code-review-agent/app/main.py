from fastapi import Depends
from fastapi import FastAPI

from .controllers import github_controller
from .utils.auth_dependancy import token_required
from fastapi.middleware.cors import CORSMiddleware

from .utils.db import init_db
from .config import get_settings

app = FastAPI(title = get_settings().APP_NAME,dependencies=[Depends(token_required)])
# app = FastAPI(title = get_settings().APP_NAME)

@app.on_event("startup")
def _startup():
    init_db()

origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(github_controller.router)