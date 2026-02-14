# UK Bank Savings Rate Web Scraper

A Python web scraper that extracts AER (Annual Equivalent Rate) savings rates for 1 Year Fixed savings products from UK banks.

## Features

- **Strong Typing**: Uses Pydantic v2 for data validation and type safety
- **Configurable**: Bank URLs and CSS selectors stored in YAML configuration file
- **Robust Parsing**: Handles various HTML structures and rate formats
- **Data Export**: Saves results to Parquet format using pandas and pyarrow
- **Comprehensive Testing**: Full test suite with pytest including Secure Trust Bank test

## Installation

Install the required dependencies:

```bash
pip install -r requirements.txt
```

## Configuration

Banks are configured in `banks_config.yaml`. Each bank entry includes:

```yaml
banks:
  - name: "Bank Name"
    url: "https://bank-website.com/savings"
    product_type: "1 Year Fixed"
    selectors:
      container: ".product-card, .savings-product"
      product_name: ".product-title, h3"
      aer_rate: ".aer-rate, .rate"
```

### Selector Notes

- Multiple CSS selectors can be provided (comma-separated) as fallbacks
- The scraper tries each selector until it finds a match
- The `product_type` field is used to filter products (case-insensitive substring match)

## Usage

### Command Line

Run the scraper to fetch rates from all configured banks:

```bash
python scraper.py
```

This will:
1. Load configuration from `banks_config.yaml`
2. Scrape all configured banks
3. Save results to `savings_rates_YYYYMMDD_HHMMSS.parquet`

### Programmatic Usage

```python
from scraper import ScraperConfig, BankScraper
from pathlib import Path

# Load configuration
config = ScraperConfig.from_yaml('banks_config.yaml')

# Create scraper
scraper = BankScraper(config, timeout=10)

# Scrape all banks
rates = scraper.scrape_all()

# Save to parquet
scraper.save_to_parquet(rates, 'output.parquet')

# Access rate data
for rate in rates:
    print(f"{rate.bank_name}: {rate.product_name} - {rate.aer_rate:.2%}")
```

### Reading Results

```python
import pandas as pd

# Read the parquet file
df = pd.read_parquet('savings_rates_20260214_123456.parquet')

# Display results
print(df[['bank_name', 'product_name', 'aer_rate_percent']])
```

## Data Model

### SavingsRate

The main data model for scraped rates:

```python
class SavingsRate(BaseModel):
    bank_name: str              # Name of the bank
    product_name: str           # Name of the savings product
    aer_rate: float            # AER as decimal (0.05 = 5%)
    url: str                   # URL where rate was found
    scraped_at: datetime       # When the data was scraped
```

**Validation Rules:**
- `aer_rate` must be between 0.0 and 1.0 (0% to 100%)
- Automatically converts percentage strings (e.g., "5.0%") to decimal format
- All models are frozen (immutable) for data integrity

## Testing

Run the test suite:

```bash
pytest test_scraper.py -v
```

### Test Coverage

- **Pydantic Model Tests**: Validation, parsing, and type checking
- **Configuration Tests**: YAML loading and parsing
- **Scraper Tests**: Rate extraction, HTML parsing, error handling
- **Secure Trust Bank Test**: Specific test for STB website structure
- **End-to-End Tests**: Complete workflow from config to parquet file

## Project Structure

```
hazel/
├── scraper.py              # Main scraper module with pydantic models
├── test_scraper.py         # Comprehensive test suite
├── banks_config.yaml       # Bank configuration file
├── requirements.txt        # Python dependencies
├── README_SCRAPER.md       # This file
└── *.parquet              # Output files (generated)
```

## Dependencies

- **requests**: HTTP library for web scraping
- **beautifulsoup4**: HTML parsing
- **lxml**: Fast XML/HTML parser
- **pandas**: Data manipulation and parquet export
- **pyarrow**: Parquet file format support
- **pydantic**: Data validation and type hints
- **pytest**: Testing framework
- **pyyaml**: YAML configuration parsing

## Error Handling

The scraper includes robust error handling:

- **Network Errors**: Catches connection failures and timeouts
- **Parsing Errors**: Continues if a specific product can't be parsed
- **Missing Elements**: Tries multiple CSS selectors before giving up
- **Rate Extraction**: Uses regex patterns to find rates in various formats

Errors are logged to console and don't stop the scraping of other banks.

## Extending

### Adding New Banks

1. Add a new entry to `banks_config.yaml`
2. Inspect the bank's website HTML structure
3. Configure appropriate CSS selectors
4. Test with: `pytest test_scraper.py -v`

### Custom Selectors

If the default selectors don't work, you can:

1. Use browser DevTools to inspect the HTML
2. Update the `selectors` section in the config
3. Provide multiple fallback selectors (comma-separated)

## Known Limitations

- Only supports 1 Year Fixed savings products (configurable per bank)
- Requires HTML structure with CSS-selectable elements
- May need selector updates if bank websites change
- No JavaScript rendering (uses static HTML only)

## Future Enhancements

Potential improvements:

- Support for JavaScript-rendered pages (Selenium/Playwright)
- Automatic selector discovery
- Rate history tracking
- Email notifications on rate changes
- Support for multiple product types
- Database storage instead of just parquet files

## License

See LICENSE file in the repository root.
