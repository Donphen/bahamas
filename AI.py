import pandas as pd
import json
import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path(__file__).with_name(".env"))

class InventoryAIFormatter:
    """
    Map CSV headers to the optimiser's schema and return only its required columns.
    Data rows are transformed locally; the AI receives only the input headers.
    """
    def __init__(self, api_key=None):
        self.client = OpenAI(
            api_key=api_key or os.getenv("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com"
        )
        # The strict schema the main file needs to run its math
        self.target_columns = [
            "Stock_Name", "Current_Quantity", "Cost_Price", 
            "Selling_Price", "Daily_Demand", "Delivery_Time_Days"
        ]

    def format_dataframe(self, raw_df):
        """Map a dataframe's columns to the schema expected by the optimiser."""
        # 2. Ask the AI to map headers; transform all rows locally.
        prompt = f"""
        Map the input CSV column names to this exact schema:
        {self.target_columns}

        Return only a JSON object with a "column_mapping" object. Use each exact input
        column name as the value, or null when no input column matches. Map product
        identifiers or names to Stock_Name, on-hand inventory to Current_Quantity,
        acquisition cost to Cost_Price, customer price to Selling_Price, sales or
        demand forecast to Daily_Demand, and supplier lead time to Delivery_Time_Days.

        Input column names: {raw_df.columns.tolist()}
        """

        # Send only the headers to the AI; rows are transformed locally.
        response = self.client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "You output only valid JSON."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.0
        )

        if not response.choices or not response.choices[0].message.content:
            raise ValueError("Bahamas AI returned an empty column mapping.")

        parsed_json = json.loads(response.choices[0].message.content)
        column_mapping = parsed_json.get("column_mapping", {})
        if not isinstance(column_mapping, dict):
            raise ValueError("Bahamas AI response must contain a column_mapping object.")

        clean_df = pd.DataFrame(index=raw_df.index)
        for target_column in self.target_columns:
            source_column = column_mapping.get(target_column)
            if isinstance(source_column, str) and source_column in raw_df.columns:
                clean_df[target_column] = raw_df[source_column]
            else:
                clean_df[target_column] = float("nan")

        for col in self.target_columns[1:]:
            clean_df[col] = pd.to_numeric(clean_df[col], errors="coerce")

        return clean_df[self.target_columns]

    def format_csv(self, file_path):
        """Read and format a CSV file for the optimiser."""
        try:
            raw_df = pd.read_csv(file_path)
            return self.format_dataframe(raw_df)
        except Exception as e:
            print(f"formatting failed: {e}")
            return None


def get_formatted_csv():
    file_path = input("Enter the CSV filename or path: ").strip().strip('"')
    if not Path(file_path).is_file():
        print("File not found")
        return None

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("Set DEEPSEEK_API_KEY in the .env file before running the formatter.")
        return None

    return InventoryAIFormatter(api_key).format_csv(file_path)