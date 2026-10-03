import os
import numpy as np
import pandas as pd
from AI import InventoryAIFormatter
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder=".")
CORS(app)

REQUIRED_COLUMNS = [
    "Stock_Name", "Current_Quantity", "Daily_Demand",
    "Delivery_Time_Days", "Cost_Price", "Selling_Price",
]


def run_optimiser(df: pd.DataFrame) -> pd.DataFrame:
    """Apply all business logic. Returns a new DataFrame with derived columns."""
    df = df.copy()

    df["Reorder_Point"] = df["Daily_Demand"] * df["Delivery_Time_Days"]
    df["Days_Of_Inventory"] = df["Current_Quantity"] / df["Daily_Demand"]
    df["Buffer_Days"] = df["Days_Of_Inventory"] - df["Delivery_Time_Days"]

    df["Stockout_Probability_%"] = np.where(
        df["Buffer_Days"] <= 0,
        99.0,
        np.maximum(0.0, 100.0 - (df["Buffer_Days"] / 14.0 * 100)),
    )

    df["Optimal_Order_Qty"] = np.maximum(
        0,
        (df["Daily_Demand"] * 30) + df["Reorder_Point"] - df["Current_Quantity"],
    )

    df["Suggested_Price"] = df["Selling_Price"]
    df.loc[df["Selling_Price"] < df["Cost_Price"] * 1.15, "Suggested_Price"] = (
        df["Cost_Price"] * 1.15
    )
    df.loc[df["Selling_Price"] > df["Cost_Price"] * 3.5, "Suggested_Price"] = (
        df["Cost_Price"] * 3.5
    )

    df["Optimized_Profit_Per_Unit"] = df["Suggested_Price"] - df["Cost_Price"]
    df["Expected_Monthly_Profit"] = (
        df["Optimized_Profit_Per_Unit"] * (df["Daily_Demand"] * 30)
    )

    # Plain-English verdicts
    def stock_action(row):
        if row["Stockout_Probability_%"] > 75:
            return "BUY NOW"
        if row["Stockout_Probability_%"] > 30:
            return "ORDER SOON"
        return "STOCK IS FINE"

    def price_action(row):
        if row["Selling_Price"] < row["Cost_Price"]:
            return "LOSING MONEY"
        if row["Selling_Price"] > row["Cost_Price"] * 3.5:
            return "TOO EXPENSIVE"
        return "PRICE IS GOOD"

    df["Stock_Action"] = df.apply(stock_action, axis=1)
    df["Price_Action"] = df.apply(price_action, axis=1)

    df = df.sort_values(by="Expected_Monthly_Profit", ascending=False).reset_index(drop=True)
    return df


def make_advice(row) -> str:
    """Short, human-readable recommendation for one item."""
    parts = []

    if row["Optimal_Order_Qty"] > 0:
        parts.append(f"Order about {row['Optimal_Order_Qty']:.0f} more units.")
    else:
        parts.append("You already have enough stock.")

    if row["Selling_Price"] < row["Cost_Price"]:
        parts.append(
            f"You are losing money. Sell at ${row['Suggested_Price']:.2f} "
            f"instead of ${row['Selling_Price']:.2f}."
        )
    elif row["Selling_Price"] > row["Cost_Price"] * 3.5:
        parts.append(
            f"You may be charging too much. Try ${row['Suggested_Price']:.2f} "
            f"instead of ${row['Selling_Price']:.2f}."
        )
    else:
        parts.append(f"Price is fine at ${row['Selling_Price']:.2f}.")

    return " ".join(parts)


# ---------- Routes ----------

@app.route("/")
def index():
    return send_from_directory(".", "dashboard.html")


@app.route("/dashboard.css")
def css():
    return send_from_directory(".", "dashboard.css")


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/api/columns", methods=["GET"])
def columns():
    """Lets the front-end tell the user what columns are expected."""
    return jsonify({"required": REQUIRED_COLUMNS})


@app.route("/api/optimise", methods=["POST"])
def optimise():
    """
    Accepts either:
      - multipart/form-data with a file field named 'file'
      - application/json with a 'rows' list of objects
    Returns a JSON model the dashboard can render.
    """
    try:
        if "file" in request.files:
            uploaded_file = request.files["file"]
            if not uploaded_file.filename:
                return jsonify({"error": "Choose a CSV file to upload."}), 400

            try:
                raw_df = pd.read_csv(uploaded_file.stream)
            except (UnicodeDecodeError, pd.errors.EmptyDataError, pd.errors.ParserError) as e:
                return jsonify({"error": f"Could not read the uploaded CSV: {e}"}), 400

            if raw_df.empty:
                return jsonify({"error": "The uploaded CSV contains no data rows."}), 400

            if not os.getenv("DEEPSEEK_API_KEY"):
                return jsonify({
                    "error": "AI file formatting is not configured. Set DEEPSEEK_API_KEY in the .env file."
                }), 503

            df = InventoryAIFormatter().format_dataframe(raw_df)
            unmapped = [
                column for column in REQUIRED_COLUMNS
                if column not in df.columns or df[column].isna().all()
            ]
            if unmapped:
                return jsonify({
                    "error": "AI could not map all required inventory columns.",
                    "missing": unmapped,
                    "required": REQUIRED_COLUMNS,
                }), 400
        elif request.is_json and "rows" in request.get_json():
            df = pd.DataFrame(request.get_json()["rows"])
        else:
            return jsonify({"error": "No file or rows provided."}), 400

        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            return jsonify({
                "error": "Missing required columns.",
                "missing": missing,
                "required": REQUIRED_COLUMNS,
            }), 400

        # numeric coercion
        for col in REQUIRED_COLUMNS:
            if col != "Stock_Name":
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=[c for c in REQUIRED_COLUMNS if c != "Stock_Name"])

        if df.empty:
            return jsonify({"error": "No valid rows after parsing."}), 400

        result = run_optimiser(df)

        items = []
        for _, row in result.iterrows():
            items.append({
                "name": row["Stock_Name"],
                "current_quantity": float(row["Current_Quantity"]),
                "daily_demand": float(row["Daily_Demand"]),
                "delivery_days": float(row["Delivery_Time_Days"]),
                "cost_price": float(row["Cost_Price"]),
                "selling_price": float(row["Selling_Price"]),
                "reorder_point": float(row["Reorder_Point"]),
                "days_of_inventory": float(row["Days_Of_Inventory"]),
                "stockout_probability": float(row["Stockout_Probability_%"]),
                "optimal_order_qty": float(row["Optimal_Order_Qty"]),
                "suggested_price": float(row["Suggested_Price"]),
                "expected_monthly_profit": float(row["Expected_Monthly_Profit"]),
                "stock_action": row["Stock_Action"],
                "price_action": row["Price_Action"],
                "advice": make_advice(row),
            })

        summary = {
            "total_items": len(items),
            "total_expected_profit": float(result["Expected_Monthly_Profit"].sum()),
            "items_to_buy_now": int((result["Stock_Action"] == "BUY NOW").sum()),
            "items_losing_money": int((result["Price_Action"] == "LOSING MONEY").sum()),
        }

        return jsonify({"summary": summary, "items": items})

    except Exception as e:
        return jsonify({"error": f"Could not process input: {e}"}), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)