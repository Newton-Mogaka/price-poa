# Implementation Summary: Add "On Offer" Banner and Savings Amount to Infographics

## Overview
Implemented enhancements to PricePoa infographic generation to display promotional information including:
1. "ON OFFER" visual indicator (enhanced existing functionality)
2. Actual savings amount extracted from promotion details

## Files Modified

### 1. `api/query_engine.py`
- **get_product_prices()**: Enhanced to pass through `promotion_details` from price documents to store entries
- **find_product_matches()**: Enhanced to pass through `promotion_details` from cheapest store to product options

### 2. `api/telegram_webhook.py`  
- **get_shopping_list_data()**: Enhanced to pass through `promotion_details` in store items (both direct products and alternative products)

### 3. `api/infographics/generator.py`
- **Added `_parse_promotion_details()` helper function**: Parses promotion details strings to extract savings information
  - Handles formats like: 'Was KES 164.00 (12.2% Off)'
  - Extracts original price and discount percentage
  - Calculates savings amount and formats for display
- **Enhanced `draw_ranked_row()` function**: 
  - Added `promotion_details` parameter
  - Displays savings information when promotion details are available
  - Shows savings as: "Save [amount] KES ([percentage]% Off)" below the price
- **Updated all three image generation functions**:
  - `generate_single_product_image()`: Pass promotion_details to draw_ranked_row
  - `generate_shopping_list_image()`: Pass promotion_details to draw_ranked_row  
  - `generate_product_options_image()`: Pass promotion_details to draw_ranked_row

## Data Flow
```
Database (NormalizedProduct.promotion_details)
        ↓
Scraping Pipeline → Prices Collection 
        ↓
API Layer (query_engine.py, telegram_webhook.py): Extract and pass through promotion_details
        ↓
Infographic Generator (api/infographics/generator.py): 
        - Parse promotion details to calculate savings
        - Enhanced visual display with savings information
        ↓
Telegram/Web Users See: Enhanced infographics with "ON OFFER" indicator and savings amounts
```

## Example
For a product with:
- Current price: 42 KES
- Promotion details: 'Was KES 164.00 (12.2% Off)'

The infographic will now display:
- Standard price display: "KES 42"
- Enhanced offer indicator: "OFFER" pill (existing)
- Savings information: "Save 20.0 KES (12.2% Off)" (new)

## Technical Details
- Promotion details are extracted using regex patterns:
  - Original price: `r'Was\s*KES\s*([\d,]+\.?\d*)'` 
  - Discount percentage: `r'\(([\d.]+)%\s*Off\)'`
- Savings amount calculated as: `original_price × (percentage / 100)`
- Amounts formatted nicely (e.g., "20.0", "1.2k" for values ≥1000)
- Graceful handling of missing or malformed promotion details