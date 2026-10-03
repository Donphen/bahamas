import pandas as pd
import json
import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path(__file__).with_name(".env"))

class InventoryAIFormatter:
    """
    This class ONLY reads a CSV, identifies column names, drops extra information, 
    leaves missing information blank, relabels columns to standard formats, 
    and returns a clean Pandas DataFrame.
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

    def format_csv(self, file_path):
        # 1. Read the raw, messy CSV
        try:
            raw_df = pd.read_csv(file_path)
        except Exception as e:
            print(f"Error reading CSV: {e}")
            return None

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

        print(" Bahamas AI is reading the CSV. please be patient.")
        
        try:
            # 3. Request only the small header mapping, not a copy of every row.
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "You output only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                response_format={ "type": "json_object" },
                temperature=0.0 # Keep temperature at 0 for strict data mapping
            )
            
            # 4. Apply the mapping locally so response size does not grow with the CSV.
            ai_output = response.choices[0].message.content
            parsed_json = json.loads(ai_output)
            column_mapping = parsed_json.get("column_mapping", {})
            if not isinstance(column_mapping, dict):
                raise ValueError("AI response must contain a column_mapping object")

            clean_df = pd.DataFrame(index=raw_df.index)
            for target_column in self.target_columns:
                source_column = column_mapping.get(target_column)
                if isinstance(source_column, str) and source_column in raw_df.columns:
                    clean_df[target_column] = raw_df[source_column]
                else:
                    clean_df[target_column] = float("nan")

            # Ensure data types are numeric where applicable so math doesn't break later
            for col in self.target_columns[1:]:
                if col in clean_df.columns:
                    clean_df[col] = pd.to_numeric(clean_df[col], errors='coerce')
            
            print("✅ Data perfectly formatted for the main script.")
            return clean_df[self.target_columns] # Return only the strict columns
            
        except Exception as e:
            print(f"❌ AI Formatting failed: {e}")
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