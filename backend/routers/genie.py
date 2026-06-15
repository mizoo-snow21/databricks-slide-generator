from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth.user_workspace import build_default_workspace_client, get_user_workspace_client
from services import genie_service
from services.genie_service import GenieSpaceInfo
from services.llm_service import LLMService

router = APIRouter(prefix="/api/genie", tags=["genie"])

_llm_service = LLMService(workspace_client=build_default_workspace_client())


def get_llm_service() -> LLMService:
    return _llm_service


class SuggestedQuestionsResponse(BaseModel):
    questions: list[str]


@router.get("/spaces", response_model=list[GenieSpaceInfo])
def list_spaces(client=Depends(get_user_workspace_client)) -> list[GenieSpaceInfo]:
    try:
        return genie_service.list_spaces(client)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Genie workspace unavailable: {exc}",
        ) from exc


@router.get("/spaces/{space_id}", response_model=GenieSpaceInfo)
def get_space(
    space_id: str,
    client=Depends(get_user_workspace_client),
) -> GenieSpaceInfo:
    try:
        return genie_service.get_space(client, space_id)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Genie workspace unavailable: {exc}",
        ) from exc


@router.post(
    "/spaces/{space_id}/suggested-questions",
    response_model=SuggestedQuestionsResponse,
)
def suggested_questions(
    space_id: str,
    client=Depends(get_user_workspace_client),
    llm: LLMService = Depends(get_llm_service),
) -> SuggestedQuestionsResponse:
    try:
        space = genie_service.get_space(client, space_id)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Genie workspace unavailable: {exc}",
        ) from exc
    try:
        questions = genie_service.suggest_questions(llm, space, n=8)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Question suggestion failed",
        ) from exc
    return SuggestedQuestionsResponse(questions=questions)
