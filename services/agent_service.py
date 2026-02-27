import os
import requests
import json
from db_config import get_connection
from services.sales_service import get_sales_trend


# -----------------------------
# CONFIG
# -----------------------------
def get_openrouter_api_key():
    return os.getenv("OPENROUTER_API_KEY", "").strip()


# -----------------------------
# DECISION ENGINE
# -----------------------------
def get_decision(context):
    api_key = get_openrouter_api_key()

    if not api_key:
        return json.dumps({
            "problem": "Missing OpenRouter API key",
            "action": "no_action",
            "discount": 0,
            "reason": "Set OPENROUTER_API_KEY in your environment"
        })

    prompt = f"""
    You are an intelligent e-commerce agent.

    Respond ONLY in valid JSON.

    Rules:
    - action must be "discount" or "no_action"
    - discount must be between 0 and 50

    Output:
    {{
        "problem": "...",
        "action": "discount",
        "discount": 10,
        "reason": "..."
    }}

    Data:
    {context}
    """

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "deepseek/deepseek-chat",
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            },
            timeout=10
        )

        response.raise_for_status()
        result = response.json()
        print("API RESPONSE:", result)

        if "choices" in result:
            return result['choices'][0]['message']['content']

        elif "error" in result:
            return json.dumps({
                "problem": "API error",
                "action": "no_action",
                "discount": 0,
                "reason": result["error"].get("message", "Unknown error")
            })

        else:
            return json.dumps({
                "problem": "Invalid response",
                "action": "no_action",
                "discount": 0,
                "reason": str(result)
            })

    except Exception as e:
        return json.dumps({
            "problem": "Request failed",
            "action": "no_action",
            "discount": 0,
            "reason": str(e)
        })


# -----------------------------
# PARSE DECISION
# -----------------------------
def parse_decision(decision_text):
    try:
        decision_text = decision_text.replace("```json", "").replace("```", "").strip()
        return json.loads(decision_text)
    except Exception as e:
        return {
            "problem": decision_text,
            "action": "no_action",
            "discount": 0,
            "reason": f"Parsing failed: {str(e)}"
        }


# -----------------------------
# MAIN AGENT LOOP
# -----------------------------
def run_agent():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM products")
    products = cursor.fetchall()

    results = []   # 🔥 IMPORTANT FOR OUTPUT

    for product in products:
        product_id = product["id"]
        price = float(product["price"])
        stock = product["stock"]

        # -------- OBSERVE --------
        trend = get_sales_trend(product_id)

        context = {
            "price": price,
            "stock": stock,
            "sales_trend": trend
        }

        # -------- DECIDE --------
        decision_text = get_decision(context)
        decision = parse_decision(decision_text)

        action = decision.get("action", "no_action")
        discount = float(decision.get("discount", 0))
        reason = decision.get("reason", "")
        problem = decision.get("problem", "")

        before_price = price
        after_price = price

        # -------- ACT --------
        if action == "discount" and discount > 0:
            after_price = round(price * (1 - discount / 100), 2)

            cursor.execute(
                "UPDATE products SET price=%s WHERE id=%s",
                (after_price, product_id)
            )

            success = True
        else:
            success = False

        # -------- LOG --------
        cursor.execute("""
            INSERT INTO agent_logs
            (product_id, problem, action, action_value, reason, before_price, after_price, success)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            product_id,
            problem,
            action,
            discount,
            reason,
            before_price,
            after_price,
            success
        ))

        conn.commit()

        # -------- STORE RESULT (FOR UI/API) --------
        results.append({
            "product_id": product_id,
            "action": action,
            "discount": discount,
            "before_price": before_price,
            "after_price": after_price,
            "reason": reason,
            "success": success
        })

    conn.close()

    return results
