from db_config import get_connection
import random


# -----------------------------
# 1. SIMULATE SALES
# -----------------------------
def simulate_sales():
    conn = get_connection()
    cursor = conn.cursor()

    # get all product ids
    cursor.execute("SELECT id FROM products")
    products = cursor.fetchall()

    for product in products:
        quantity = random.randint(1, 5)

        cursor.execute(
            "INSERT INTO sales (product_id, quantity) VALUES (%s, %s)",
            (product[0], quantity)
        )

    conn.commit()
    conn.close()

    return "Sales simulated successfully"


# -----------------------------
# 2. SALES TREND (FOR AGENT)
# -----------------------------
def get_sales_trend(product_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT SUM(quantity) FROM sales WHERE product_id=%s",
        (product_id,)
    )

    total = cursor.fetchone()[0] or 0

    conn.close()

    # simple logic for demo clarity
    if total > 20:
        return "up"
    elif total < 10:
        return "down"
    else:
        return "stable"