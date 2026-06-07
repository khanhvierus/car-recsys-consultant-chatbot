import threading
from typing import List, Optional

from pydantic import BaseModel, Field


class CoreSlots(BaseModel):
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    body_type: Optional[str] = None
    fuel_type: Optional[str] = None
    brand: Optional[str] = None
    condition: Optional[str] = None


class SoftPreferences(BaseModel):
    features: List[str] = Field(default_factory=list)
    vibe: Optional[str] = None


class UserProfile(BaseModel):
    core_slots: CoreSlots = Field(default_factory=CoreSlots)
    soft_preferences: SoftPreferences = Field(default_factory=SoftPreferences)
    viewed_models: List[str] = Field(default_factory=list)
    excluded_brands: List[str] = Field(default_factory=list)


class ProfileUpdate(BaseModel):
    budget_min: Optional[float] = Field(default=None, description="Minimum budget as a USD number.")
    budget_max: Optional[float] = Field(default=None, description="Maximum budget as a USD number.")
    body_type: Optional[str] = Field(default=None, description="Desired body or usage type, e.g. SUV, Sedan.")
    fuel_type: Optional[str] = Field(default=None, description="Desired fuel type, e.g. Gasoline, Hybrid, Electric.")
    brand: Optional[str] = Field(default=None, description="Preferred brand if any.")
    condition: Optional[str] = Field(default=None, description="New or Used.")
    add_features: List[str] = Field(default_factory=list, description="New desired features to remember.")
    vibe: Optional[str] = Field(default=None, description="Overall vibe the customer wants, e.g. luxurious, sporty.")
    exclude_brands: List[str] = Field(default_factory=list, description="Brands the customer wants to avoid.")
    interested_models: List[str] = Field(default_factory=list, description="Specific models the customer asks about.")


def merge_update(profile: UserProfile, update: ProfileUpdate) -> UserProfile:
    cs = profile.core_slots
    for field in ("budget_min", "budget_max", "body_type", "fuel_type", "brand", "condition"):
        value = getattr(update, field)
        if value is not None:
            setattr(cs, field, value)
    sp = profile.soft_preferences
    for feature in update.add_features:
        if feature and feature not in sp.features:
            sp.features.append(feature)
    if update.vibe:
        sp.vibe = update.vibe
    for brand in update.exclude_brands:
        if brand and brand not in profile.excluded_brands:
            profile.excluded_brands.append(brand)
    for model in update.interested_models:
        if model and model not in profile.viewed_models:
            profile.viewed_models.append(model)
    return profile


def log_viewed(profile: UserProfile, titles: List[str]) -> UserProfile:
    for title in titles:
        if title and title not in profile.viewed_models:
            profile.viewed_models.append(title)
    return profile


# --- in-memory persistence (was file JSON; Cloud Run fs is ephemeral) ---
_PROFILES: dict[str, UserProfile] = {}
_LOCK = threading.Lock()


def load_profile(session_id: str) -> UserProfile:
    with _LOCK:
        return _PROFILES.get(session_id) or UserProfile()


def save_profile(session_id: str, profile: UserProfile) -> None:
    with _LOCK:
        _PROFILES[session_id] = profile


def delete_profile(session_id: str) -> None:
    with _LOCK:
        _PROFILES.pop(session_id, None)
