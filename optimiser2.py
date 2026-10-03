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
    safe_demand = df["Daily_Demand"].where(df["Daily_Demand"] != 0)
    df["Days_Of_Inventory"] = df["Current_Quantity"] / safe_demand
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

    price_inputs_available = (
        df["Selling_Price"].notna()
        & df["Cost_Price"].notna()
        & (df["Cost_Price"] > 0)
    )
    df["Suggested_Price"] = df["Selling_Price"].where(price_inputs_available)
    below_minimum = price_inputs_available & (df["Selling_Price"] < df["Cost_Price"] * 1.15)
    above_maximum = price_inputs_available & (df["Selling_Price"] > df["Cost_Price"] * 3.5)
    df.loc[below_minimum, "Suggested_Price"] = df.loc[below_minimum, "Cost_Price"] * 1.15
    df.loc[above_maximum, "Suggested_Price"] = df.loc[above_maximum, "Cost_Price"] * 3.5

    df["Optimized_Profit_Per_Unit"] = df["Suggested_Price"] - df["Cost_Price"]
    df["Expected_Monthly_Profit"] = (
        df["Optimized_Profit_Per_Unit"] * (df["Daily_Demand"] * 30)
    )

    # Plain-English verdicts
    def stock_action(row):
        if pd.isna(row["Stockout_Probability_%"]):
            return "INSUFFICIENT DATA"
        if row["Stockout_Probability_%"] > 75:
            return "BUY NOW"
        if row["Stockout_Probability_%"] > 30:
            return "ORDER SOON"
        return "STOCK IS FINE"

    def price_action(row):
        if pd.isna(row["Selling_Price"]) or pd.isna(row["Cost_Price"]) or row["Cost_Price"] <= 0:
            return "INSUFFICIENT DATA"
        if row["Selling_Price"] < row["Cost_Price"]:
            return "LOSING MONEY"
        if row["Selling_Price"] > row["Cost_Price"] * 3.5:
            return "TOO EXPENSIVE"
        return "PRICE IS GOOD"

    df["Stock_Action"] = df.apply(stock_action, axis=1)
    df["Price_Action"] = df.apply(price_action, axis=1)

    df = df.sort_values(by="Expected_Monthly_Profit", ascending=False).reset_index(drop=True)
    return df


def _rand(amount) -> str:
    """Format a number as South African Rand, e.g. R2 800.00"""
    return "R" + f"{amount:,.2f}".replace(",", " ")


def make_advice(row) -> str:
    """Short, human-readable recommendation for one item."""
    parts = []

    if pd.isna(row["Optimal_Order_Qty"]):
        parts.append("Stock advice unavailable because required inputs are missing.")
    elif row["Optimal_Order_Qty"] > 0:
        parts.append(f"Order about {row['Optimal_Order_Qty']:.0f} more units.")
    else:
        parts.append("You already have enough stock.")

    if pd.isna(row["Selling_Price"]) or pd.isna(row["Cost_Price"]) or row["Cost_Price"] <= 0:
        parts.append("Price advice unavailable because required inputs are missing.")
    elif row["Selling_Price"] < row["Cost_Price"]:
        parts.append(

            f"You are losing money. Sell at {_rand(row['Suggested_Price'])} "
            f"instead of {_rand(row['Selling_Price'])}."
        )
    elif row["Selling_Price"] > row["Cost_Price"] * 3.5:
        parts.append(
            f"You may be charging too much. Try {_rand(row['Suggested_Price'])} "
            f"instead of {_rand(row['Selling_Price'])}."
        )
    else:
        parts.append(f"Price is fine at {_rand(row['Selling_Price'])}.")

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
        elif request.is_json and "rows" in request.get_json():
            df = pd.DataFrame(request.get_json()["rows"])
        else:
            return jsonify({"error": "No file or rows provided."}), 400

        for column in REQUIRED_COLUMNS:
            if column not in df.columns:
                df[column] = np.nan

        df["Stock_Name"] = df["Stock_Name"].replace(r"^\s*$", np.nan, regex=True)

        # Preserve partial rows; only reject files missing most of the schema.
        for column in REQUIRED_COLUMNS:
            if column != "Stock_Name":
                df[column] = pd.to_numeric(df[column], errors="coerce")

        missing = [column for column in REQUIRED_COLUMNS if df[column].isna().all()]
        if len(missing) > 4:
            return jsonify({
                "error": "Insufficient information: more than four required columns are missing.",
                "missing": missing,
                "required": REQUIRED_COLUMNS,
            }), 400

        df = df.dropna(subset=REQUIRED_COLUMNS, how="all").copy()
        if df.empty:
            return jsonify({"error": "No valid rows after parsing."}), 400

        df["Stock_Name"] = df["Stock_Name"].fillna("Unnamed item")

        result = run_optimiser(df)

        def json_number(value):
            return float(value) if pd.notna(value) else None

        items = []
        for _, row in result.iterrows():
            items.append({
                "name": row["Stock_Name"],
                "current_quantity": json_number(row["Current_Quantity"]),
                "daily_demand": json_number(row["Daily_Demand"]),
                "delivery_days": json_number(row["Delivery_Time_Days"]),
                "cost_price": json_number(row["Cost_Price"]),
                "selling_price": json_number(row["Selling_Price"]),
                "reorder_point": json_number(row["Reorder_Point"]),
                "days_of_inventory": json_number(row["Days_Of_Inventory"]),
                "stockout_probability": json_number(row["Stockout_Probability_%"]),
                "optimal_order_qty": json_number(row["Optimal_Order_Qty"]),
                "suggested_price": json_number(row["Suggested_Price"]),
                "expected_monthly_profit": json_number(row["Expected_Monthly_Profit"]),
                "stock_action": row["Stock_Action"],
                "price_action": row["Price_Action"],
                "advice": make_advice(row),
            })

        summary = {
            "total_items": len(items),
            "total_expected_profit": json_number(
                result["Expected_Monthly_Profit"].sum(min_count=1)
            ),
            "items_to_buy_now": int((result["Stock_Action"] == "BUY NOW").sum()),
            "items_losing_money": int((result["Price_Action"] == "LOSING MONEY").sum()),
        }

        return jsonify({"summary": summary, "items": items})

    except Exception as e:
        return jsonify({"error": f"Could not process input: {e}"}), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)