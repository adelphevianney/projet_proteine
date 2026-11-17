"""Modèles Pydantic des requêtes (première ligne de validation ; la base est la seconde)."""
from __future__ import annotations

from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

Phone = Field(pattern=r"^\+?[0-9]{8,15}$")


class OtpRequest(BaseModel):
    phone: str = Phone


class OtpVerify(BaseModel):
    phone: str = Phone
    code: str = Field(pattern=r"^[0-9]{6}$")


class Signup(BaseModel):
    signup_token: str
    name: str = Field(min_length=2, max_length=80)
    role: Literal["producer", "farm", "breeder", "collector"]
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lng: Optional[float] = Field(default=None, ge=-180, le=180)
    commune: Optional[str] = None
    is_woman: bool = False


class ProfileUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=80)
    commune: Optional[str] = None
    is_woman: Optional[bool] = None
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lng: Optional[float] = Field(default=None, ge=-180, le=180)


class OfferText(BaseModel):
    text: str = Field(min_length=3, max_length=300)


class OfferCreate(BaseModel):
    waste_type_id: Literal["manioc", "cajou", "cacao", "marche"]
    quantity_kg: Decimal = Field(gt=0, le=1_000_000)
    price_per_kg: Optional[int] = Field(default=None, ge=0, le=10_000)
    frequency: str = "ponctuelle"
    description: Optional[str] = Field(default=None, max_length=300)
    commune: Optional[str] = None
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lng: Optional[float] = Field(default=None, ge=-180, le=180)


class OfferUpdate(BaseModel):
    quantity_kg: Optional[Decimal] = Field(default=None, gt=0, le=1_000_000)
    price_per_kg: Optional[int] = Field(default=None, ge=0, le=10_000)
    frequency: Optional[str] = None
    description: Optional[str] = Field(default=None, max_length=300)
    commune: Optional[str] = None
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lng: Optional[float] = Field(default=None, ge=-180, le=180)


class Collect(BaseModel):
    weight_kg: Decimal = Field(gt=0, le=1_000_000)


class Receive(BaseModel):
    quality: Literal["conforme", "degrade", "rejete"]


class Recall(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


class FlourCreate(BaseModel):
    source_lot_ids: list[UUID] = Field(min_length=1)
    quantity_kg: Decimal = Field(gt=0, le=1_000_000)
    price_per_kg: int = Field(gt=0, le=100_000)


class OrderCreate(BaseModel):
    flour_batch_id: UUID
    quantity_kg: Decimal = Field(gt=0, le=1_000_000)


class PaymentConfirm(BaseModel):
    reference: str = Field(min_length=4, max_length=80)


class RationRequest(BaseModel):
    profile_id: str
    soy_price: Optional[int] = Field(default=None, gt=0, le=5000)
    headcount: Optional[int] = Field(default=None, gt=0, le=1_000_000)
    days: Optional[int] = Field(default=None, gt=0, le=365)
    save: bool = False


class HerdCreate(BaseModel):
    profile_id: str
    name: str = Field(min_length=2, max_length=80)
    headcount: int = Field(gt=0, le=1_000_000)


class PriceReport(BaseModel):
    item: str
    price_fcfa_kg: int = Field(gt=0, le=1_000_000)
    commune: Optional[str] = None


class DisputeCreate(BaseModel):
    subject: str = Field(min_length=3, max_length=120)
    body: str = Field(min_length=3, max_length=2000)
    ref_code: Optional[str] = None


class DisputeResolve(BaseModel):
    resolution: str = Field(min_length=3, max_length=2000)
