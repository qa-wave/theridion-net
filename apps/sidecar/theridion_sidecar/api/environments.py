"""CRUD endpoints for request environments."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import environments
from ..environments import Environment, EnvironmentSummary, EnvVariable

router = APIRouter(prefix="/api/environments", tags=["environments"])


class CreateEnvironmentInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


class RenameEnvironmentInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


class ReplaceVariablesInput(BaseModel):
    variables: list[EnvVariable]


@router.get("", response_model=list[EnvironmentSummary])
def list_environments() -> list[EnvironmentSummary]:
    return environments.list_summaries()


@router.post("", response_model=Environment, status_code=201)
def create_environment(body: CreateEnvironmentInput) -> Environment:
    return environments.create(body.name)


@router.get("/{env_id}", response_model=Environment)
def get_environment(env_id: str) -> Environment:
    env = environments.get(env_id)
    if env is None:
        raise HTTPException(status_code=404, detail="environment not found")
    return env


@router.patch("/{env_id}", response_model=Environment)
def rename_environment(env_id: str, body: RenameEnvironmentInput) -> Environment:
    try:
        return environments.rename(env_id, body.name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.put("/{env_id}/variables", response_model=Environment)
def replace_variables(env_id: str, body: ReplaceVariablesInput) -> Environment:
    try:
        return environments.replace_variables(env_id, body.variables)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.delete("/{env_id}", status_code=204)
def delete_environment(env_id: str) -> None:
    if not environments.delete(env_id):
        raise HTTPException(status_code=404, detail="environment not found")
