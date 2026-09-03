"""Payment gateway placeholder. Real providers (Razorpay, Stripe...) subclass PaymentGateway and register in GATEWAYS."""
from flask import abort, current_app

from . import db


class PaymentGateway:
    name = ""

    def create_checkout(self, payment):
        """payment is the payments row (dict). Return {"redirect_url": ...} or {"client_payload": ...}."""
        raise NotImplementedError

    def handle_webhook(self, request):
        """Verify the provider callback, set the row's status to paid/failed, return the updated row."""
        raise NotImplementedError


class DummyGateway(PaymentGateway):
    """No real charge. Mark a payment by POSTing {"payment_id": N, "status": "paid"} to /api/v1/payments/webhook/dummy."""
    name = "dummy"

    def create_checkout(self, payment):
        db.update("payments", payment["id"], {"provider_ref": f"dummy-{payment['id']}"})
        return {"redirect_url": f"/api/v1/payments/dummy/{payment['id']}"}

    def handle_webhook(self, request):
        body = request.get_json(silent=True) or {}
        payment = db.one(db.table("payments").select("*").eq("id", int(body.get("payment_id") or 0))) or abort(404)
        if body.get("status") not in ("paid", "failed"):
            abort(400, "status must be paid or failed")
        return db.update("payments", payment["id"], {"status": body["status"], "raw": body})


GATEWAYS = {"dummy": DummyGateway()}


def gateway():
    return GATEWAYS[current_app.config["PAYMENT_PROVIDER"]]
