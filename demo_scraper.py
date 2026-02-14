#!/usr/bin/env python3
"""
demo_scraper.py

Demonstration script showing how to use the UK Bank Savings Rate scraper.
This example shows both the basic usage and advanced features.
"""

from pathlib import Path
from datetime import datetime
import pandas as pd

from scraper import (
    ScraperConfig,
    BankScraper,
    BankConfig,
    BankSelectors,
    SavingsRate,
)


def demo_basic_usage():
    """Demonstrate basic usage: load config, scrape, save."""
    print("=== Basic Usage Demo ===\n")
    
    # Load configuration from YAML file
    config_path = Path(__file__).parent / 'banks_config.yaml'
    config = ScraperConfig.from_yaml(config_path)
    
    print(f"Loaded configuration with {len(config.banks)} banks:")
    for bank in config.banks:
        print(f"  - {bank.name}")
    print()
    
    # Create scraper instance
    scraper = BankScraper(config, timeout=10)
    
    # Scrape all banks
    print("Scraping banks...")
    rates = scraper.scrape_all()
    print(f"Total rates found: {len(rates)}\n")
    
    # Display results
    if rates:
        print("Results:")
        for rate in rates:
            print(f"  {rate.bank_name}: {rate.product_name}")
            print(f"    AER: {rate.aer_rate:.2%}")
            print(f"    Scraped at: {rate.scraped_at.strftime('%Y-%m-%d %H:%M:%S')}")
            print()
        
        # Save to parquet
        output_path = Path(__file__).parent / 'demo_output.parquet'
        scraper.save_to_parquet(rates, output_path)
        print(f"Saved to: {output_path}")
    else:
        print("No rates were found (this is expected if websites are not accessible)")
    
    print()


def demo_custom_bank():
    """Demonstrate adding a custom bank programmatically."""
    print("=== Custom Bank Demo ===\n")
    
    # Create a custom bank configuration
    selectors = BankSelectors(
        container=".rate-card, .savings-product",
        product_name=".product-name, h3",
        aer_rate=".aer, .rate"
    )
    
    custom_bank = BankConfig(
        name="Custom Demo Bank",
        url="https://example.com/savings",
        product_type="1 Year Fixed",
        selectors=selectors
    )
    
    print(f"Created custom bank config:")
    print(f"  Name: {custom_bank.name}")
    print(f"  URL: {custom_bank.url}")
    print(f"  Product Type: {custom_bank.product_type}")
    print()
    
    # Create scraper with custom configuration
    config = ScraperConfig(banks=[custom_bank])
    scraper = BankScraper(config)
    
    # This would scrape the custom bank
    # rates = scraper.scrape_bank(custom_bank)
    print("(Scraping not performed in demo mode)")
    print()


def demo_read_parquet():
    """Demonstrate reading and analyzing saved parquet data."""
    print("=== Reading Parquet Data Demo ===\n")
    
    # Check if demo output exists
    output_path = Path(__file__).parent / 'demo_output.parquet'
    
    if output_path.exists():
        # Read the parquet file
        df = pd.read_parquet(output_path)
        
        print(f"Loaded {len(df)} records from {output_path.name}\n")
        
        # Display summary
        print("Summary Statistics:")
        print(f"  Banks: {df['bank_name'].nunique()}")
        print(f"  Average AER: {df['aer_rate'].mean():.2%}")
        print(f"  Max AER: {df['aer_rate'].max():.2%}")
        print(f"  Min AER: {df['aer_rate'].min():.2%}")
        print()
        
        # Display detailed data
        print("Detailed Data:")
        print(df[['bank_name', 'product_name', 'aer_rate_percent']].to_string(index=False))
        print()
    else:
        print(f"Demo output file not found: {output_path}")
        print("Run demo_basic_usage() first to create the file.")
        print()


def demo_pydantic_validation():
    """Demonstrate pydantic validation features."""
    print("=== Pydantic Validation Demo ===\n")
    
    # Create a valid savings rate
    print("Creating a valid SavingsRate:")
    rate1 = SavingsRate(
        bank_name="Demo Bank",
        product_name="1 Year Fixed Saver",
        aer_rate="5.25%",  # String with percentage
        url="https://example.com"
    )
    print(f"  Bank: {rate1.bank_name}")
    print(f"  Product: {rate1.product_name}")
    print(f"  AER: {rate1.aer_rate:.2%} (parsed from '5.25%')")
    print()
    
    # Demonstrate automatic conversion
    print("Automatic percentage conversion:")
    test_values = ["5.0%", "5.0", "0.05"]
    for val in test_values:
        rate = SavingsRate(
            bank_name="Test",
            product_name="Test",
            aer_rate=val,
            url="https://example.com"
        )
        print(f"  Input: '{val}' -> Decimal: {rate.aer_rate}")
    print()
    
    # Demonstrate validation errors
    print("Validation example (negative rate):")
    try:
        invalid_rate = SavingsRate(
            bank_name="Test",
            product_name="Test",
            aer_rate=-0.05,
            url="https://example.com"
        )
    except Exception as e:
        print(f"  ✗ Correctly rejected: {type(e).__name__}")
    print()
    
    # Demonstrate immutability
    print("Immutability example:")
    try:
        rate1.aer_rate = 0.10
        print("  ✗ Model is mutable (unexpected!)")
    except Exception:
        print("  ✓ Model is frozen (immutable)")
    print()


def main():
    """Run all demos."""
    print("\n" + "="*60)
    print("UK Bank Savings Rate Scraper - Demonstration")
    print("="*60 + "\n")
    
    # Run demos
    demo_basic_usage()
    demo_custom_bank()
    demo_pydantic_validation()
    demo_read_parquet()
    
    print("="*60)
    print("Demo complete!")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
