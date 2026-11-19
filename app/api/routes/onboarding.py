"""Account-scoped workspace tour preference; no external service is needed."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, StrictBool

from app.services.auth import get_member_user
from app.services.database import get_user_setting, set_user_setting

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])
PREFERENCE = "workspace_tour_v1_dismissed"


class TourPreference(BaseModel):
    dismissed: StrictBool


@router.get("")
def get_tour_preference(user: dict = Depends(get_member_user)):
    return {"dismissed": get_user_setting(user["user_id"], PREFERENCE, "false") == "true"}


@router.put("")
def set_tour_preference(body: TourPreference, user: dict = Depends(get_member_user)):
    set_user_setting(user["user_id"], PREFERENCE, str(body.dismissed).lower())
    return {"dismissed": body.dismissed}
