from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import Principal, get_current_principal
from app.core.config import get_settings
from app.core.database import get_db
from app.schemas.help import HelpAnswer, HelpAskRequest, HelpOverview
from app.services.help_assistant import ask_help, get_help_overview

router = APIRouter(prefix="/api/v1/help", tags=["help"])


@router.get("")
def read_help_overview(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> HelpOverview:
    return get_help_overview(db, principal)


@router.post("/ask")
def create_help_answer(
    payload: HelpAskRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> HelpAnswer:
    return ask_help(
        db,
        principal,
        get_settings(),
        question=payload.question,
        history=payload.history,
    )
