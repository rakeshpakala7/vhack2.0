import os
import random
from flask import Flask, jsonify, render_template, request
from services.product_service import get_all_products
from services.sales_service import simulate_sales, get_sales_trend
from services.agent_service import run_agent
from db_config import get_connection

app = Flask(__name__)

DEMO_PRODUCTS = [
    {"id": 1, "name": "Noise Buds Pro", "price": 89.0, "stock": 28, "category": "Audio"},
    {"id": 2, "name": "Aero Smart Watch X", "price": 149.0, "stock": 19, "category": "Wearables"},
    {"id": 3, "name": "PowerMax 20K Bank", "price": 59.0, "stock": 42, "category": "Accessories"},
    {"id": 4, "name": "TrimEdge Groom Kit", "price": 69.0, "stock": 25, "category": "Grooming"},
    {"id": 5, "name": "Volt Gaming Mouse", "price": 39.0, "stock": 31, "category": "Gaming"},
    {"id": 6, "name": "AirCool Desk Fan", "price": 45.0, "stock": 15, "category": "Home"},
]

UI_STATE = {
    "likes": set(),
    "wishlist": set(),
    "cart": {},
    "demo_logs": []
}


def _db_is_available():
    try:
        conn = get_connection()
        conn.close()
        return True
    except Exception:
        return False


def _competitor_price(price, product_id):
    gap_factor = ((product_id * 17) % 21 - 10) / 100
    return round(price * (1 + gap_factor), 2)


def _normalize_products(rows):
    normalized = []
    for row in rows:
        product_id = int(row.get("id"))
        normalized.append({
            "id": product_id,
            "name": row.get("name", f"Product {product_id}"),
            "price": float(row.get("price", 0)),
            "stock": int(row.get("stock", 0)),
            "category": row.get("category", "General")
        })
    return normalized


def _get_products():
    if _db_is_available():
        return _normalize_products(get_all_products()), "db"
    return [dict(p) for p in DEMO_PRODUCTS], "demo"


def _trend_for_product(product, source):
    if source == "db":
        try:
            return get_sales_trend(product["id"])
        except Exception:
            pass

    demand = _demand_for_product(product, source)
    if demand >= 75:
        return "up"
    if demand <= 35:
        return "down"
    return "stable"


def _demand_for_product(product, source):
    if source == "db":
        try:
            trend = get_sales_trend(product["id"])
            if trend == "up":
                return 82
            if trend == "down":
                return 34
            return 56
        except Exception:
            pass
    return max(20, min(95, 100 - product["stock"] + ((product["id"] * 11) % 21)))


def _product_image_url(product_id):
    return f"https://picsum.photos/seed/shop-{product_id}/480/320"


def _enrich_products(products, source):
    enriched = []
    for p in products:
        competitor = _competitor_price(p["price"], p["id"])
        demand = _demand_for_product(p, source)
        trend = _trend_for_product(p, source)
        cart_qty = int(UI_STATE["cart"].get(p["id"], 0))
        enriched.append({
            **p,
            "demand": demand,
            "sales_trend": trend,
            "competitor_price": competitor,
            "price_gap_percent": 0 if p["price"] == 0 else round(((p["price"] - competitor) / p["price"]) * 100, 2),
            "liked": p["id"] in UI_STATE["likes"],
            "wishlisted": p["id"] in UI_STATE["wishlist"],
            "cart_qty": cart_qty,
            "image_url": _product_image_url(p["id"])
        })
    return enriched


def _build_cart_summary(enriched_products):
    by_id = {p["id"]: p for p in enriched_products}
    items = []
    total = 0.0
    for pid, qty in UI_STATE["cart"].items():
        product = by_id.get(pid)
        if not product:
            continue
        subtotal = round(product["price"] * qty, 2)
        total += subtotal
        items.append({
            "product_id": pid,
            "name": product["name"],
            "quantity": qty,
            "price": product["price"],
            "subtotal": subtotal
        })
    return {
        "items": items,
        "count": sum(item["quantity"] for item in items),
        "total": round(total, 2)
    }


def _record_demo_log(log):
    UI_STATE["demo_logs"].insert(0, log)
    UI_STATE["demo_logs"] = UI_STATE["demo_logs"][:80]


def _run_demo_agent(products, source):
    results = []
    for p in products:
        demand = _demand_for_product(p, source)
        competitor = _competitor_price(p["price"], p["id"])
        action = "no_action"
        discount = 0.0
        reason = "Market conditions are balanced."

        if p["stock"] > 32 and demand < 45:
            action = "discount"
            discount = 12.0
            reason = "High stock and weak demand detected."
        elif competitor < p["price"] and demand < 60:
            action = "discount"
            discount = 6.0
            reason = "Competitor undercutting while demand is soft."
        elif p["stock"] < 8 and demand > 70:
            reason = "Protecting margin due to low stock and strong demand."

        before_price = p["price"]
        after_price = before_price
        success = False

        if action == "discount" and discount > 0:
            after_price = round(before_price * (1 - discount / 100), 2)
            p["price"] = after_price
            success = True

        log = {
            "product_id": p["id"],
            "problem": f"demand={demand}, stock={p['stock']}, competitor={competitor}",
            "action": action,
            "action_value": discount,
            "reason": reason,
            "before_price": before_price,
            "after_price": after_price,
            "success": success
        }
        _record_demo_log(log)
        results.append(log)

    return results


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/store-data")
def store_data():
    products, source = _get_products()
    enriched = _enrich_products(products, source)
    return jsonify({
        "ok": True,
        "source": source,
        "products": enriched,
        "cart": _build_cart_summary(enriched),
        "wishlist_count": len(UI_STATE["wishlist"]),
        "likes_count": len(UI_STATE["likes"])
    })


@app.route("/products")
def products():
    products_data, source = _get_products()
    return jsonify(_enrich_products(products_data, source))


@app.route("/competitor-prices")
def competitor_prices():
    products_data, source = _get_products()
    comparison = []
    for product in products_data:
        our_price = float(product["price"])
        rival_price = _competitor_price(our_price, int(product["id"]))
        gap_percent = 0 if our_price == 0 else round(((our_price - rival_price) / our_price) * 100, 2)
        comparison.append({
            "product_id": int(product["id"]),
            "name": product["name"],
            "our_price": our_price,
            "competitor_price": rival_price,
            "gap_percent": gap_percent,
            "source": source
        })
    return jsonify({"ok": True, "data": comparison})


@app.route("/business-signals")
def business_signals():
    products_data, source = _get_products()
    signals = []
    for product in products_data:
        stock = int(product["stock"])
        price = float(product["price"])
        rival_price = _competitor_price(price, int(product["id"]))
        trend = _trend_for_product(product, source)
        stock_risk = "high" if stock <= 5 else ("medium" if stock <= 15 else "low")
        signals.append({
            "product_id": int(product["id"]),
            "name": product["name"],
            "sales_trend": trend,
            "stock_risk": stock_risk,
            "stock": stock,
            "demand": _demand_for_product(product, source),
            "price_gap": round(price - rival_price, 2),
            "source": source
        })
    return jsonify({"ok": True, "data": signals})


@app.route("/strategy-preview")
def strategy_preview():
    products_data, source = _get_products()
    plans = []
    for product in products_data:
        base_price = float(product["price"])
        options = [
            {"strategy": "hold_price", "projected_profit": round(base_price * 0.30 * 8, 2), "impact": "stable margin"},
            {"strategy": "discount_8_percent", "projected_profit": round(base_price * 0.22 * 11, 2), "impact": "higher conversion"},
            {"strategy": "campaign_boost", "projected_profit": round(base_price * 0.27 * 10, 2), "impact": "demand stimulation"}
        ]
        chosen = max(options, key=lambda x: x["projected_profit"])
        plans.append({
            "product_id": int(product["id"]),
            "name": product["name"],
            "context": {
                "trend": _trend_for_product(product, source),
                "stock": int(product["stock"]),
                "demand": _demand_for_product(product, source),
                "our_price": base_price,
                "competitor_price": _competitor_price(base_price, int(product["id"]))
            },
            "options": options,
            "selected": chosen,
            "reason": "Selected by projected profit score with margin safeguards.",
            "source": source
        })
    return jsonify({"ok": True, "data": plans})


@app.route("/simulate-sales")
def simulate():
    products_data, source = _get_products()
    if source == "db":
        try:
            return jsonify({"ok": True, "message": simulate_sales(), "source": source})
        except Exception as e:
            return jsonify({"ok": False, "error": "simulate_sales_failed", "message": str(e)}), 500

    for p in DEMO_PRODUCTS:
        swing = random.randint(-2, 4)
        p["stock"] = max(1, p["stock"] - max(0, swing))
    return jsonify({"ok": True, "message": "Sales simulated successfully (demo mode)", "source": source})


@app.route("/toggle-like", methods=["POST"])
def toggle_like():
    payload = request.get_json(silent=True) or {}
    product_id = int(payload.get("product_id", 0))
    if product_id in UI_STATE["likes"]:
        UI_STATE["likes"].remove(product_id)
        liked = False
    else:
        UI_STATE["likes"].add(product_id)
        liked = True
    return jsonify({"ok": True, "product_id": product_id, "liked": liked})


@app.route("/wishlist/toggle", methods=["POST"])
def toggle_wishlist():
    payload = request.get_json(silent=True) or {}
    product_id = int(payload.get("product_id", 0))
    if product_id in UI_STATE["wishlist"]:
        UI_STATE["wishlist"].remove(product_id)
        wishlisted = False
    else:
        UI_STATE["wishlist"].add(product_id)
        wishlisted = True
    return jsonify({"ok": True, "product_id": product_id, "wishlisted": wishlisted})


@app.route("/cart/add", methods=["POST"])
def cart_add():
    payload = request.get_json(silent=True) or {}
    product_id = int(payload.get("product_id", 0))
    quantity = max(1, int(payload.get("quantity", 1)))
    UI_STATE["cart"][product_id] = int(UI_STATE["cart"].get(product_id, 0)) + quantity
    return jsonify({"ok": True, "product_id": product_id, "quantity": UI_STATE["cart"][product_id]})


@app.route("/cart/remove", methods=["POST"])
def cart_remove():
    payload = request.get_json(silent=True) or {}
    product_id = int(payload.get("product_id", 0))
    if product_id in UI_STATE["cart"]:
        del UI_STATE["cart"][product_id]
    return jsonify({"ok": True, "product_id": product_id})


@app.route("/cart")
def cart():
    products_data, source = _get_products()
    enriched = _enrich_products(products_data, source)
    return jsonify({"ok": True, "cart": _build_cart_summary(enriched)})


@app.route("/simulate-purchase", methods=["POST"])
def simulate_purchase():
    payload = request.get_json(silent=True) or {}

    try:
        product_id = int(payload.get("product_id", 0))
        quantity = max(1, int(payload.get("quantity", 1)))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "invalid_payload", "message": "product_id and quantity must be numbers"}), 400

    products_data, source = _get_products()
    product = next((p for p in products_data if int(p["id"]) == product_id), None)
    if not product:
        return jsonify({"ok": False, "error": "product_not_found"}), 404

    stock = int(product["stock"])
    if quantity > stock:
        return jsonify({"ok": False, "error": "insufficient_stock", "available_stock": stock}), 400

    if source == "db":
        try:
            conn = get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("UPDATE products SET stock = stock - %s WHERE id = %s", (quantity, product_id))
            cursor.execute("INSERT INTO sales (product_id, quantity) VALUES (%s, %s)", (product_id, quantity))
            conn.commit()
            conn.close()
        except Exception as e:
            return jsonify({"ok": False, "error": "purchase_simulation_failed", "message": str(e)}), 500
    else:
        for p in DEMO_PRODUCTS:
            if p["id"] == product_id:
                p["stock"] = max(0, p["stock"] - quantity)
                break

    UI_STATE["cart"][product_id] = max(0, int(UI_STATE["cart"].get(product_id, 0)) - quantity)

    unit_price = float(product["price"])
    return jsonify({
        "ok": True,
        "message": "Purchase simulated",
        "source": source,
        "order": {
            "product_id": product_id,
            "name": product["name"],
            "quantity": quantity,
            "unit_price": unit_price,
            "total": round(unit_price * quantity, 2)
        }
    })


@app.route("/run-agent")
def run():
    products_data, source = _get_products()
    if source == "db":
        try:
            return jsonify(run_agent())
        except Exception:
            pass
    return jsonify(_run_demo_agent(products_data, source))


@app.route("/agent-logs")
def agent_logs():
    limit = int(request.args.get("limit", 30))
    limit = max(1, min(limit, 100))
    if _db_is_available():
        try:
            conn = get_connection()
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute("SELECT * FROM agent_logs ORDER BY id DESC LIMIT %s", (limit,))
            except Exception:
                cursor.execute("SELECT * FROM agent_logs LIMIT %s", (limit,))
            rows = cursor.fetchall()
            conn.close()
            return jsonify({"ok": True, "data": rows, "source": "db"})
        except Exception:
            pass
    return jsonify({"ok": True, "data": UI_STATE["demo_logs"][:limit], "source": "demo"})


@app.route("/health")
def health():
    db_ok = _db_is_available()
    api_key_ok = bool(os.getenv("OPENROUTER_API_KEY", "").strip())
    data_source = "db" if db_ok else "demo"
    status_code = 200 if data_source == "db" and api_key_ok else 206
    return jsonify({
        "ok": db_ok and api_key_ok,
        "mode": data_source,
        "services": {
            "database": {"ok": db_ok},
            "openrouter_api_key": {"ok": api_key_ok}
        }
    }), status_code


if __name__ == "__main__":
    app.run(debug=True)
