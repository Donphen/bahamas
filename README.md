# Bahamas Inventory Optimizer

A Flask web app for analyzing inventory, estimating reorder quantities and stockout risk, and reviewing pricing recommendations. The dashboard is served locally and displays results in South African rand (ZAR).

## Features

- Upload a CSV and use DeepSeek to map its column names to the inventory schema.
- Submit already formatted rows as JSON without using the AI formatter.
- Calculate reorder points, inventory days, stockout risk, suggested prices, and expected monthly profit.
- Continue with partial data when four or fewer required columns are wholly missing. Metrics that need unavailable values are left unavailable. More than four wholly missing required columns returns an insufficient-information error.

## Requirements

- Python 3.10 or later
- A DeepSeek API key for CSV uploads

## Setup on Windows

Run these commands from the repository folder in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Create a `.env` file in the repository root for CSV uploads:

```dotenv
DEEPSEEK_API_KEY=your_deepseek_api_key
```

Keep `.env` private. It is excluded from Git. The JSON API does not require the key.

## Run the Dashboard

Start the Flask server from the repository root:

```powershell
python optimiser2.py
```

The filename is `optimiser2.py` (British spelling). Open <http://127.0.0.1:5000> in a browser. Select a CSV and choose **Analyze**.

## CSV Schema

The formatter maps CSV headers to these fields:

| Field                | Meaning                        | Type   |
| -------------------- | ------------------------------ | ------ |
| `Stock_Name`         | Product or stock item name     | Text   |
| `Current_Quantity`   | Current units in stock         | Number |
| `Daily_Demand`       | Average units demanded per day | Number |
| `Delivery_Time_Days` | Supplier delivery lead time    | Number |
| `Cost_Price`         | Cost per unit, in ZAR          | Number |
| `Selling_Price`      | Selling price per unit, in ZAR | Number |

For CSV uploads, the AI maps source headers and the application converts numeric fields. Missing cells remain unavailable rather than being treated as zero. If all values are missing for more than four of the six required fields, the upload is rejected. The included `retail_store_inventory.csv` has already been mapped to this schema and includes generated cost and delivery-time data.

Other sample datasets in the repository include `bakery_data.csv`, `gym_data.csv`, and `inventory_data.csv`.

## API

### `GET /api/health`

Returns the server status:

```json
{ "status": "ok" }
```

### `GET /api/columns`

Returns the required inventory fields.

### `POST /api/optimise`

Accepts either a CSV upload as multipart form data, with the file field named `file`, or JSON with a `rows` array:

```json
{
  "rows": [
    {
      "Stock_Name": "T-Shirt",
      "Current_Quantity": 120,
      "Daily_Demand": 8,
      "Delivery_Time_Days": 5,
      "Cost_Price": 12.5,
      "Selling_Price": 20
    }
  ]
}
```

The response contains a `summary` and an `items` array with per-item calculations, verdicts, and advice. Unavailable calculations are returned as `null`.

## Included Files

- `optimiser2.py`: Flask application, API routes, and inventory calculations.
- `AI.py`: DeepSeek-based CSV header mapper.
- `dashboard.html` and `dashboard.css`: Browser interface.
- `requirements.txt`: Python dependencies.
