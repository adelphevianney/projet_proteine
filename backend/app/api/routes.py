"""Routes de l'API /api/v1. Chaque route vérifie le rôle puis délègue à un service métier."""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query

from .. import schemas as s
from ..domain import (accounts, changes, community, flour, impact, lots, offers, orders, payments, rations,
                      trace)
from ..security import current_user, require

router = APIRouter(prefix="/api/v1")

producer = require("producer")
farm = require("farm")
breeder = require("breeder")
collector = require("collector")
admin = require("admin")
farm_or_admin = require("farm", "admin")


# --- Comptes -------------------------------------------------------------------------------
@router.post("/auth/otp/request", tags=["comptes"])
def otp_request(body: s.OtpRequest):
    return accounts.request_otp(body.phone)


@router.post("/auth/otp/verify", tags=["comptes"])
def otp_verify(body: s.OtpVerify):
    return accounts.verify_otp(body.phone, body.code)


@router.post("/auth/signup", tags=["comptes"])
def signup(body: s.Signup):
    return accounts.signup(body.signup_token, body.name, body.role, body.lat, body.lng, body.commune, body.is_woman)


@router.get("/me", tags=["comptes"])
def me(user=Depends(current_user)):
    return user


@router.patch("/me", tags=["comptes"])
def update_me(body: s.ProfileUpdate, user=Depends(current_user)):
    return accounts.update_profile(user, body.model_dump())


@router.get("/me/history", tags=["comptes"])
def my_history(user=Depends(current_user)):
    return accounts.profile_history(user["id"])


# --- Référentiels -------------------------------------------------------------------------------
@router.get("/animal-profiles", tags=["référentiels"])
def animal_profiles():
    return rations.profiles()


@router.get("/ingredients", tags=["référentiels"])
def ingredients():
    return rations.ingredients()


# --- Offres et lots ------------------------------------------------------------------------------
@router.post("/offers/parse", tags=["offres"])
def parse_offer(body: s.OfferText):
    return offers.parse_text(body.text)


@router.post("/offers", tags=["offres"])
def create_offer(body: s.OfferCreate, user=Depends(producer)):
    return offers.create(user, body.model_dump())


@router.get("/offers/mine", tags=["offres"])
def my_offers(user=Depends(producer)):
    return offers.mine(user)


@router.patch("/offers/{offer_id}", tags=["offres"])
def update_offer(offer_id: UUID, body: s.OfferUpdate, user=Depends(producer)):
    return offers.update(user, offer_id, body.model_dump())


@router.post("/offers/{offer_id}/cancel", tags=["offres"])
def cancel_offer(offer_id: UUID, user=Depends(producer)):
    return offers.cancel(user, offer_id)


@router.get("/offers/{offer_id}/history", tags=["offres"])
def offer_history(offer_id: UUID, user=Depends(current_user)):
    return offers.history(offer_id)


@router.get("/offers/nearby", tags=["offres"])
def nearby_offers(lat: Optional[float] = None, lng: Optional[float] = None, km: float = Query(50, gt=0, le=500),
                  user=Depends(farm)):
    return offers.nearby(user, lat, lng, km)


@router.post("/offers/{offer_id}/reserve", tags=["offres"])
def reserve_offer(offer_id: UUID, user=Depends(farm)):
    return offers.reserve(user, offer_id)


@router.get("/lots", tags=["lots"])
def my_lots(user=Depends(require())):
    return lots.for_user(user)


@router.get("/tour", tags=["lots"])
def my_tour(user=Depends(collector)):
    return lots.tour(user)


@router.post("/lots/{lot_id}/collect", tags=["lots"])
def collect_lot(lot_id: UUID, body: s.Collect, user=Depends(collector)):
    return lots.collect(user, lot_id, body.weight_kg)


@router.post("/lots/{lot_id}/receive", tags=["lots"])
def receive_lot(lot_id: UUID, body: s.Receive, user=Depends(farm)):
    return lots.receive(user, lot_id, body.quality)


@router.post("/lots/{lot_id}/recall", tags=["traçabilité"])
def recall_lot(lot_id: UUID, body: s.Recall, user=Depends(farm_or_admin)):
    return lots.recall(user, lot_id, body.reason)


# --- Farine et commandes --------------------------------------------------------------------------
@router.post("/flour-batches", tags=["farine"])
def declare_flour(body: s.FlourCreate, user=Depends(farm)):
    return flour.declare(user, body.source_lot_ids, body.quantity_kg, body.price_per_kg)


@router.get("/flour-batches/mine", tags=["farine"])
def my_flour(user=Depends(farm)):
    return flour.mine(user)


@router.get("/flour-batches/available", tags=["farine"])
def available_flour(lat: Optional[float] = None, lng: Optional[float] = None, user=Depends(breeder)):
    return flour.available(user, lat, lng)


@router.post("/flour-batches/{batch_id}/recall", tags=["traçabilité"])
def recall_flour(batch_id: UUID, body: s.Recall, user=Depends(farm_or_admin)):
    return lots.recall_flour(user, batch_id, body.reason)


@router.post("/orders", tags=["commandes"])
def create_order(body: s.OrderCreate, user=Depends(breeder),
                 idempotency_key: Optional[str] = Header(default=None, max_length=100)):
    return orders.create(user, body.flour_batch_id, body.quantity_kg, idempotency_key)


@router.get("/orders/mine", tags=["commandes"])
def my_orders(user=Depends(breeder)):
    return orders.mine(user)


@router.get("/orders/incoming", tags=["commandes"])
def incoming_orders(user=Depends(farm)):
    return orders.incoming(user)


@router.post("/orders/{order_id}/deliver", tags=["commandes"])
def deliver_order(order_id: UUID, user=Depends(farm)):
    return orders.deliver(user, order_id)


@router.post("/orders/{order_id}/cancel", tags=["commandes"])
def cancel_order(order_id: UUID, user=Depends(breeder)):
    return orders.cancel(user, order_id)


# --- Paiements -------------------------------------------------------------------------------------
@router.get("/payments", tags=["paiements"])
def my_payments(user=Depends(require())):
    return payments.mine(user)


@router.post("/payments/{payment_id}/confirm", tags=["paiements"])
def confirm_payment(payment_id: UUID, body: s.PaymentConfirm, user=Depends(require())):
    return payments.confirm(user, payment_id, body.reference)


# --- Formulateur et élevages ------------------------------------------------------------------------
@router.post("/rations/compute", tags=["formulateur"])
def compute_ration(body: s.RationRequest, user=Depends(current_user)):
    return rations.compute(user, body.profile_id, body.soy_price, body.headcount, body.days, body.save)


@router.post("/herds", tags=["formulateur"])
def add_herd(body: s.HerdCreate, user=Depends(breeder)):
    return community.add_herd(user, body.profile_id, body.name, body.headcount)


@router.get("/herds", tags=["formulateur"])
def my_herds(user=Depends(breeder)):
    return community.herds(user)


# --- Traçabilité, prix, litiges, notifications, impact, changements -------------------------------
@router.get("/trace/{code}", tags=["traçabilité"])
def trace_code(code: str):
    return trace.trace(code)


@router.get("/prices", tags=["prix"])
def prices():
    return community.community_prices()


@router.post("/prices", tags=["prix"])
def report_price(body: s.PriceReport, user=Depends(require())):
    return community.report_price(user, body.item, body.price_fcfa_kg, body.commune)


@router.post("/disputes", tags=["litiges"])
def open_dispute(body: s.DisputeCreate, user=Depends(current_user)):
    return community.open_dispute(user, body.subject, body.body, body.ref_code)


@router.get("/disputes/mine", tags=["litiges"])
def my_disputes(user=Depends(current_user)):
    return community.my_disputes(user)


@router.get("/notifications", tags=["notifications"])
def my_notifications(user=Depends(current_user)):
    return community.notifications(user)


@router.post("/notifications/read", tags=["notifications"])
def read_notifications(user=Depends(current_user)):
    return community.mark_read(user)


@router.get("/impact", tags=["impact"])
def get_impact(user=Depends(current_user)):
    return impact.impact(user)


@router.get("/changes", tags=["changements"])
def get_changes(since: Optional[str] = Query(default=None, pattern=r"^[0-9]+(:[0-9]+:[0-9]+)?$"), user=Depends(current_user)):
    return changes.changes_since(user, since)


# --- Administration ---------------------------------------------------------------------------------
@router.get("/admin/users", tags=["administration"])
def admin_users(status: Optional[str] = None, role: Optional[str] = None, user=Depends(admin)):
    return accounts.list_users(status, role)


@router.post("/admin/users/{user_id}/validate", tags=["administration"])
def admin_validate(user_id: UUID, user=Depends(admin)):
    return accounts.set_status(user, user_id, "active")


@router.post("/admin/users/{user_id}/disable", tags=["administration"])
def admin_disable(user_id: UUID, user=Depends(admin)):
    return accounts.set_status(user, user_id, "disabled")


@router.get("/admin/disputes", tags=["administration"])
def admin_disputes(status: Optional[str] = None, user=Depends(admin)):
    return community.all_disputes(status)


@router.post("/admin/disputes/{dispute_id}/resolve", tags=["administration"])
def admin_resolve(dispute_id: UUID, body: s.DisputeResolve, user=Depends(admin)):
    return community.resolve_dispute(user, dispute_id, body.resolution)


@router.get("/admin/payments", tags=["administration"])
def admin_payments(status: Optional[str] = None, user=Depends(admin)):
    return payments.all_payments(status)
