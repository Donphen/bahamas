import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from AI import get_formatted_csv

df = get_formatted_csv()
if df is None:
    raise SystemExit(1)
print(df.to_string(index=False))


df['Reorder_Point'] = df['Daily_Demand'] * df['Delivery_Time_Days']

df['Days_Of_Inventory'] = df['Current_Quantity'].div(
    df['Daily_Demand'].where(df['Daily_Demand'] != 0)
)
df['Buffer_Days'] = df['Days_Of_Inventory'] - df['Delivery_Time_Days']

df['Stockout_Probability_%'] = np.where(
    df['Buffer_Days'] <= 0, 99.0,
    np.maximum(0.0, 100.0 - (df['Buffer_Days'] / 14.0 * 100))
)

df['Optimal_Order_Qty'] = np.maximum(0, (df['Daily_Demand'] * 30) + df['Reorder_Point'] - df['Current_Quantity'])

df['Current_Profit_Per_Unit'] = df['Selling_Price'] - df['Cost_Price']
df['Current_Margin_%'] = (
    df['Current_Profit_Per_Unit'] / df['Cost_Price'].where(df['Cost_Price'] != 0)
) * 100

price_inputs_available = df['Selling_Price'].notna() & df['Cost_Price'].notna() & (df['Cost_Price'] > 0)
df['Suggested_Price'] = df['Selling_Price'].where(price_inputs_available)
below_minimum_price = price_inputs_available & (df['Selling_Price'] < df['Cost_Price'] * 1.15)
above_maximum_price = price_inputs_available & (df['Selling_Price'] > df['Cost_Price'] * 3.5)
df.loc[below_minimum_price, 'Suggested_Price'] = df.loc[below_minimum_price, 'Cost_Price'] * 1.15
df.loc[above_maximum_price, 'Suggested_Price'] = df.loc[above_maximum_price, 'Cost_Price'] * 3.5

df['Optimized_Profit_Per_Unit'] = df['Suggested_Price'] - df['Cost_Price']

df['Expected_Monthly_Profit'] = df['Optimized_Profit_Per_Unit'] * (df['Daily_Demand'] * 30)
df = df.sort_values(by='Expected_Monthly_Profit', ascending=False).reset_index(drop=True)

plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['text.color'] = '#37352f'
plt.rcParams['axes.labelcolor'] = '#787774'
plt.rcParams['xtick.color'] = '#787774'
plt.rcParams['ytick.color'] = '#787774'
COLORS = {
    'dark': '#37352f',
    'green': '#a1c2a8',
    'red': '#d99c9c',
    'yellow': '#d9c89c',
    'gray': '#ebeced'
}

fig = plt.figure(figsize=(14, 10))
fig.patch.set_facecolor('#ffffff')
fig.suptitle('Stock Optimization & Profit Maximization Dashboard', fontsize=20, fontweight='bold', color=COLORS['dark'])

ax1 = plt.subplot(2, 2, 1)
x = np.arange(len(df['Stock_Name']))
width = 0.35
ax1.bar(x - width/2, df['Current_Quantity'], width, label='Current Stock', color=COLORS['dark'])
ax1.bar(x + width/2, df['Reorder_Point'], width, label='Reorder Point', color=COLORS['red'])
ax1.set_title('Current Stock vs. Reorder Threshold')
ax1.set_xticks(x)
ax1.set_xticklabels(df['Stock_Name'], rotation=15)
ax1.legend()
ax1.spines['top'].set_visible(False)
ax1.spines['right'].set_visible(False)

ax2 = plt.subplot(2, 2, 2)
bars = ax2.barh(df['Stock_Name'], df['Stockout_Probability_%'], color=COLORS['gray'])
for i, bar in enumerate(bars):
    prob = df['Stockout_Probability_%'].iloc[i]
    if prob > 75: bar.set_color(COLORS['red'])
    elif prob > 30: bar.set_color(COLORS['yellow'])
    else: bar.set_color(COLORS['green'])
ax2.set_title('Probability of Stockout Before Delivery (%)')
ax2.set_xlim(0, 100)
ax2.invert_yaxis()
ax2.spines['top'].set_visible(False)
ax2.spines['right'].set_visible(False)

ax3 = plt.subplot(2, 2, 3)
positive_profit_df = df[df['Expected_Monthly_Profit'] > 0]
pie_colors = [COLORS['dark'], COLORS['green'], COLORS['yellow'], COLORS['red'], '#b5b5b5']
if positive_profit_df.empty:
    ax3.text(0.5, 0.5, 'No positive profit data available', ha='center', va='center', color=COLORS['gray'])
    ax3.set_axis_off()
else:
    ax3.pie(positive_profit_df['Expected_Monthly_Profit'], 
            labels=positive_profit_df['Stock_Name'], 
            autopct='%1.1f%%', 
            startangle=90, 
            colors=pie_colors,
            textprops={'color': COLORS['dark']})
ax3.set_title('Which Stock to Buy More (Expected Monthly Profit)')

ax4 = plt.subplot(2, 2, 4)
ax4.plot(df['Stock_Name'], df['Cost_Price'], marker='o', label='Cost Price', color=COLORS['dark'], linestyle='--')
ax4.plot(df['Stock_Name'], df['Selling_Price'], marker='x', label='Old Selling Price', color=COLORS['red'], linestyle='')
ax4.plot(df['Stock_Name'], df['Suggested_Price'], marker='s', label='Optimized Suggested Price', color=COLORS['green'], markersize=8)
ax4.set_title('Price Correction (Preventing Overcharge & Loss)')
ax4.set_xticks(range(len(df['Stock_Name'])))
ax4.set_xticklabels(df['Stock_Name'], rotation=15)
ax4.legend()
ax4.spines['top'].set_visible(False)
ax4.spines['right'].set_visible(False)

plt.tight_layout(rect=[0, 0.03, 1, 0.95])

print("\n--- INVENTORY & PROFIT OPTIMIZATION REPORT ---")
for index, row in df.iterrows():
    print(f"\nItem: {row['Stock_Name']}")
    if pd.notna(row['Current_Quantity']):
        print(f"  - Current Stock: {row['Current_Quantity']}")
    if pd.notna(row['Reorder_Point']):
        print(f"  - Reorder Point: {row['Reorder_Point']}")
    if pd.notna(row['Stockout_Probability_%']):
        print(f"  - Stockout Risk: {row['Stockout_Probability_%']:.1f}%")
    if pd.notna(row['Optimal_Order_Qty']):
        print(f"  - Optimal Order Qty: {row['Optimal_Order_Qty']:.0f} units")
    if pd.isna(row['Cost_Price']) or pd.isna(row['Selling_Price']) or row['Cost_Price'] <= 0:
        print("  - Price optimization skipped (missing or zero cost/price input).")
    elif row['Selling_Price'] < row['Cost_Price']:
        print(f"  - ALERT: Running at a LOSS. Change price from ${row['Selling_Price']:.2f} to ${row['Suggested_Price']:.2f}")
    elif row['Selling_Price'] > row['Cost_Price'] * 3.5:
        print(f"  - ALERT: Overcharging risk. Change price from ${row['Selling_Price']:.2f} to ${row['Suggested_Price']:.2f}")
    else:
        print(f"  - Price healthy at ${row['Selling_Price']:.2f}.")

plt.show()