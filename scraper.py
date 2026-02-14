"""
scraper.py

Web scraper for UK bank savings rates (AER) for 1 Year Fixed savings products.
Uses pydantic for strong typing and pandas for data export to parquet format.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path

import requests
from bs4 import BeautifulSoup
import pandas as pd
import yaml
from pydantic import BaseModel, Field, field_validator, ConfigDict


class BankSelectors(BaseModel):
    """CSS selectors for extracting data from bank websites."""
    
    container: str = Field(..., description="CSS selector for product container")
    product_name: str = Field(..., description="CSS selector for product name")
    aer_rate: str = Field(..., description="CSS selector for AER rate")
    
    model_config = ConfigDict(frozen=True)


class BankConfig(BaseModel):
    """Configuration for a single bank's scraping parameters."""
    
    name: str = Field(..., description="Bank name")
    url: str = Field(..., description="URL to scrape")
    product_type: str = Field(..., description="Product type to search for (e.g., '1 Year Fixed')")
    selectors: BankSelectors = Field(..., description="CSS selectors for data extraction")
    
    model_config = ConfigDict(frozen=True)


class SavingsRate(BaseModel):
    """Represents a savings rate scraped from a bank website."""
    
    bank_name: str = Field(..., description="Name of the bank")
    product_name: str = Field(..., description="Name of the savings product")
    aer_rate: float = Field(..., description="Annual Equivalent Rate (AER) as decimal", ge=0.0, le=1.0)
    url: str = Field(..., description="URL where the rate was found")
    scraped_at: datetime = Field(default_factory=datetime.now, description="Timestamp when data was scraped")
    
    @field_validator('aer_rate', mode='before')
    @classmethod
    def parse_aer_rate(cls, v: Any) -> float:
        """Parse AER rate from string or float to decimal format."""
        if isinstance(v, float):
            return v
        if isinstance(v, str):
            # Remove % sign and convert to decimal
            v = v.strip().replace('%', '').strip()
            # Handle various formats like "5.0", "5.00", "5"
            try:
                rate = float(v)
                # If rate is > 1, assume it's in percentage format
                if rate > 1:
                    return rate / 100.0
                return rate
            except ValueError:
                raise ValueError(f"Unable to parse AER rate: {v}")
        raise ValueError(f"Invalid AER rate type: {type(v)}")
    
    model_config = ConfigDict(frozen=True)


class ScraperConfig(BaseModel):
    """Configuration for the web scraper."""
    
    banks: List[BankConfig] = Field(..., description="List of banks to scrape")
    
    @classmethod
    def from_yaml(cls, config_path: str | Path) -> ScraperConfig:
        """Load configuration from YAML file."""
        with open(config_path, 'r') as f:
            data = yaml.safe_load(f)
        
        # Parse banks with selectors
        banks = []
        for bank_data in data['banks']:
            selectors = BankSelectors(**bank_data['selectors'])
            bank = BankConfig(
                name=bank_data['name'],
                url=bank_data['url'],
                product_type=bank_data['product_type'],
                selectors=selectors
            )
            banks.append(bank)
        
        return cls(banks=banks)


class BankScraper:
    """Web scraper for UK bank savings rates."""
    
    def __init__(self, config: ScraperConfig, timeout: int = 10):
        """
        Initialize the scraper.
        
        Args:
            config: Scraper configuration with bank details
            timeout: HTTP request timeout in seconds
        """
        self.config = config
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
        })
    
    def _extract_rate_from_text(self, text: str) -> Optional[float]:
        """
        Extract a rate from text using regex patterns.
        
        Args:
            text: Text potentially containing a rate
            
        Returns:
            Float rate as decimal, or None if not found
        """
        # Look for patterns like "5.0%", "5.00%", "5%", "5.0", etc.
        patterns = [
            r'(\d+\.\d+)\s*%',  # "5.0%"
            r'(\d+)\.(\d+)',     # "5.0"
            r'(\d+)\s*%',        # "5%"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    if pattern == r'(\d+)\.(\d+)':
                        rate_str = match.group(0)
                    else:
                        rate_str = match.group(1) if '%' in pattern else match.group(0)
                    
                    rate = float(rate_str.replace('%', ''))
                    if rate > 1:
                        return rate / 100.0
                    return rate
                except (ValueError, IndexError):
                    continue
        
        return None
    
    def scrape_bank(self, bank: BankConfig) -> List[SavingsRate]:
        """
        Scrape savings rates from a single bank.
        
        Args:
            bank: Bank configuration
            
        Returns:
            List of scraped savings rates
        """
        rates = []
        
        try:
            response = self.session.get(bank.url, timeout=self.timeout)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'lxml')
            
            # Try to find product containers
            selectors = bank.selectors.container.split(', ')
            containers = []
            for selector in selectors:
                containers.extend(soup.select(selector.strip()))
            
            if not containers:
                print(f"Warning: No product containers found for {bank.name} using selectors: {bank.selectors.container}")
                return rates
            
            # Process each container
            for container in containers:
                try:
                    # Extract product name
                    product_name = None
                    for name_selector in bank.selectors.product_name.split(', '):
                        name_elem = container.select_one(name_selector.strip())
                        if name_elem:
                            product_name = name_elem.get_text(strip=True)
                            break
                    
                    # Check if this is the product we're looking for
                    if not product_name or bank.product_type.lower() not in product_name.lower():
                        continue
                    
                    # Extract AER rate
                    aer_rate = None
                    for rate_selector in bank.selectors.aer_rate.split(', '):
                        rate_elem = container.select_one(rate_selector.strip())
                        if rate_elem:
                            rate_text = rate_elem.get_text(strip=True)
                            aer_rate = self._extract_rate_from_text(rate_text)
                            if aer_rate:
                                break
                    
                    # If rate not found in specific element, search in all text
                    if not aer_rate:
                        container_text = container.get_text()
                        aer_rate = self._extract_rate_from_text(container_text)
                    
                    if aer_rate and product_name:
                        rate = SavingsRate(
                            bank_name=bank.name,
                            product_name=product_name,
                            aer_rate=aer_rate,
                            url=bank.url
                        )
                        rates.append(rate)
                
                except Exception as e:
                    print(f"Error processing container for {bank.name}: {e}")
                    continue
        
        except requests.RequestException as e:
            print(f"Error fetching {bank.name}: {e}")
        except Exception as e:
            print(f"Unexpected error scraping {bank.name}: {e}")
        
        return rates
    
    def scrape_all(self) -> List[SavingsRate]:
        """
        Scrape all banks in the configuration.
        
        Returns:
            List of all scraped savings rates
        """
        all_rates = []
        
        for bank in self.config.banks:
            print(f"Scraping {bank.name}...")
            rates = self.scrape_bank(bank)
            all_rates.extend(rates)
            print(f"  Found {len(rates)} rate(s)")
        
        return all_rates
    
    def save_to_parquet(self, rates: List[SavingsRate], output_path: str | Path) -> None:
        """
        Save scraped rates to a parquet file using pandas.
        
        Args:
            rates: List of savings rates to save
            output_path: Path to output parquet file
        """
        if not rates:
            print("No rates to save")
            return
        
        # Convert to DataFrame
        data = [
            {
                'bank_name': rate.bank_name,
                'product_name': rate.product_name,
                'aer_rate': rate.aer_rate,
                'aer_rate_percent': rate.aer_rate * 100,  # Also store as percentage for readability
                'url': rate.url,
                'scraped_at': rate.scraped_at
            }
            for rate in rates
        ]
        
        df = pd.DataFrame(data)
        
        # Save to parquet
        df.to_parquet(output_path, engine='pyarrow', index=False)
        print(f"Saved {len(rates)} rate(s) to {output_path}")


def main():
    """Main entry point for the scraper."""
    # Load configuration
    config_path = Path(__file__).parent / 'banks_config.yaml'
    config = ScraperConfig.from_yaml(config_path)
    
    # Create scraper
    scraper = BankScraper(config)
    
    # Scrape all banks
    rates = scraper.scrape_all()
    
    # Save to parquet
    if rates:
        output_path = Path(__file__).parent / f'savings_rates_{datetime.now().strftime("%Y%m%d_%H%M%S")}.parquet'
        scraper.save_to_parquet(rates, output_path)
    else:
        print("No rates were scraped")


if __name__ == "__main__":
    main()
