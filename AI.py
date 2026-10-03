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
    adds missing information (as 0), relabels columns to standard formats, 
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
            raw_csv_text = raw_df.to_csv(index=False)
        except Exception as e:
            print(f"Error reading CSV: {e}")
            return None

        # 2. Instruct the AI on exactly how to format the data
        prompt = f"""
        You are a strict data formatting algorithm. 
        I am giving you a raw CSV file. I need it mapped to this exact schema:
        {self.target_columns}

        Rules:
        1. Identify differently labeled columns (e.g., 'Item Name' or 'Product') and map them to 'Stock_Name'.
        2. DROP any extra information or columns that are not in the exact schema list.
        3. If a required schema column is completely missing from the raw data, add it and put the number 0 for every row.
        4. If a specific cell is blank or null, put the number 0.
        5. Output strictly a JSON object containing a key "formatted_data" which holds an array of the cleaned row objects. 
        """

        print("🤖 AI is reading the CSV, dropping extras, relabeling, and filling blanks with 0...")
        
        try:
            # 3. Call the API
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "You output only valid JSON."},
                    {"role": "user", "content": prompt + "\n\nRaw CSV:\n" + raw_csv_text}
                ],
                response_format={ "type": "json_object" },
                temperature=0.0 # Keep temperature at 0 for strict data mapping
            )
            
            # 4. Parse the output into a clean DataFrame
            ai_output = response.choices[0].message.content
            parsed_json = json.loads(ai_output)
            clean_data = parsed_json.get("formatted_data", [])
            
            clean_df = pd.DataFrame(clean_data)

            for col in self.target_columns:
                if col not in clean_df.columns:
                    clean_df[col] = 0

            # Ensure data types are numeric where applicable so math doesn't break later
            for col in self.target_columns[1:]:
                if col in clean_df.columns:
                    clean_df[col] = pd.to_numeric(clean_df[col], errors='coerce').fillna(0)
            
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