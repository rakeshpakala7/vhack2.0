import os
import random
from flask import Flask, jsonify, render_template, request
from services.product_service import get_all_products
from services.sales_service import simulate_sales, get_sales_trend
from db_config import get_connection

app = Flask(__name__)

DEMO_PRODUCTS = [
    {"id": 1, "name": "Stainless Steel Water Bottle", "price": 699.0, "stock": 44, "category": "Kitchen"},
    {"id": 2, "name": "Wireless Gaming Mouse", "price": 1499.0, "stock": 26, "category": "Gaming"},
    {"id": 3, "name": "Portable Power Bank", "price": 1299.0, "stock": 38, "category": "Accessories"},
    {"id": 4, "name": "LED Desk Lamp", "price": 899.0, "stock": 19, "category": "Home"},
    {"id": 5, "name": "Wireless Bluetooth Headphones", "price": 2499.0, "stock": 21, "category": "Audio"},
    {"id": 6, "name": "Smart Fitness Watch", "price": 3299.0, "stock": 14, "category": "Wearables"},
    {"id": 7, "name": "Running Shoes", "price": 2799.0, "stock": 32, "category": "Fashion"},
    {"id": 8, "name": "Men's Casual T-Shirt", "price": 799.0, "stock": 55, "category": "Fashion"},
    {"id": 9, "name": "Kitchen Mixer Grinder", "price": 3699.0, "stock": 12, "category": "Appliances"},
]
REQUESTED_PRODUCT_NAMES = {p["name"] for p in DEMO_PRODUCTS}
PRODUCT_IMAGE_FILES = {
    "Stainless Steel Water Bottle": "stainless_steel_water_bottle.svg",
    "Wireless Gaming Mouse": "wireless_gaming_mouse.svg",
    "Portable Power Bank": "portable_power_bank.svg",
    "LED Desk Lamp": "led_desk_lamp.svg",
    "Wireless Bluetooth Headphones": "wireless_bluetooth_headphones.svg",
    "Smart Fitness Watch": "smart_fitness_watch.svg",
    "Running Shoes": "running_shoes.svg",
    "Men's Casual T-Shirt": "mens_casual_tshirt.svg",
    "Kitchen Mixer Grinder": "kitchen_mixer_grinder.svg",
}

UI_STATE = {
    "likes": set(),
    "wishlist": set(),
    "cart": {},
    "demo_logs": [],
    "pending_decisions": []
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
        db_products = _normalize_products(get_all_products())
        filtered = [p for p in db_products if p["name"] in REQUESTED_PRODUCT_NAMES]
        if filtered:
            return filtered, "db"
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


def _product_image_url(product_name, product_id):
    filename = PRODUCT_IMAGE_FILES.get(str(product_name), f"product_{int(product_id)}.svg")
    return f"/static/images/{filename}"


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
            "image_url": _product_image_url(p["name"], p["id"])
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
        trend = _trend_for_product(p, source)
        stock = int(p["stock"])
        price = float(p["price"])

        action = "decrease_price"
        action_value = 2.0
        reason = "Baseline micro-adjustment to keep price movement active."

        if demand >= 70 and stock <= 15:
            action = "increase_price"
            action_value = 8.0
            reason = "Demand is high and stock is low."
        elif stock >= 40 and demand <= 45:
            action = "decrease_price"
            action_value = 10.0
            reason = "Stock is high and demand is weak."
        elif competitor < price and demand < 60:
            action = "decrease_price"
            action_value = 6.0
            reason = "Competitor price is lower while demand is not strong."
        elif competitor > price and trend == "up" and demand > 68:
            action = "increase_price"
            action_value = 4.0
            reason = "Demand trend is up and competitor is priced higher."
        elif demand >= 55 or stock <= 20:
            action = "increase_price"
            action_value = 3.0
            reason = "Healthy demand or tighter stock supports a small increase."

        if action == "increase_price":
            after_price = round(price * (1 + action_value / 100), 2)
        else:
            after_price = round(price * (1 - action_value / 100), 2)

        results.append({
            "product_id": p["id"],
            "name": p["name"],
            "problem": f"demand={demand}, stock={stock}, competitor={competitor}, trend={trend}",
            "action": action,
            "action_value": action_value,
            "reason": reason,
            "before_price": price,
            "after_price": after_price,
            "success": False
        })
    return results


def _analyze_agent(products, source):
    decisions = _run_demo_agent(products, source)
    UI_STATE["pending_decisions"] = decisions
    return decisions


def _apply_agent_decisions(source):
    decisions = list(UI_STATE["pending_decisions"])
    if not decisions:
        return []

    by_id = {p["id"]: p for p in DEMO_PRODUCTS}

    if source == "db":
        conn = get_connection()
        cursor = conn.cursor()

    applied = []
    for decision in decisions:
        action = decision.get("action", "no_action")
        product_id = int(decision.get("product_id", 0))
        after_price = float(decision.get("after_price", 0))
        success = action in ("increase_price", "decrease_price") and after_price > 0

        if success:
            if source == "db":
                cursor.execute("UPDATE products SET price=%s WHERE id=%s", (after_price, product_id))
            else:
                target = by_id.get(product_id)
                if target:
                    target["price"] = after_price

        log = {
            **decision,
            "success": success
        }

        if source == "db":
            cursor.execute("""
                INSERT INTO agent_logs
                (product_id, problem, action, action_value, reason, before_price, after_price, success)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                product_id,
                decision.get("problem", ""),
                action,
                float(decision.get("action_value", 0)),
                decision.get("reason", ""),
                float(decision.get("before_price", 0)),
                after_price,
                success
            ))

        _record_demo_log(log)
        applied.append(log)

    if source == "db":
        conn.commit()
        conn.close()

    UI_STATE["pending_decisions"] = []
    return applied


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
    decisions = _analyze_agent(products_data, source)
    return jsonify({
        "ok": True,
        "stage": "analysis",
        "message": "Analysis completed. Review and apply decisions.",
        "data": decisions
    })


@app.route("/apply-agent-decisions", methods=["POST"])
def apply_agent_decisions():
    _, source = _get_products()
    try:
        applied = _apply_agent_decisions(source)
    except Exception as e:
        return jsonify({"ok": False, "error": "apply_failed", "message": str(e)}), 500

    if not applied:
        return jsonify({
            "ok": False,
            "error": "no_pending_decisions",
            "message": "Run agent analysis before applying decisions."
        }), 400

    return jsonify({
        "ok": True,
        "stage": "applied",
        "message": "Price changes applied successfully.",
        "data": applied
    })


@app.route("/agent-state")
def agent_state():
    pending = UI_STATE.get("pending_decisions", [])
    return jsonify({
        "ok": True,
        "pending_count": len(pending),
        "has_pending": len(pending) > 0
    })


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
