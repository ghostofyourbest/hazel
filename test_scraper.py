"""
test_scraper.py

Unit tests for the UK bank savings rate scraper.
Tests include validation of pydantic models, scraping logic, and Secure Trust Bank specific test.

Run with: pytest test_scraper.py -v
"""

from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pandas as pd
import pytest
from bs4 import BeautifulSoup

from scraper import (
    BankConfig,
    BankSelectors,
    SavingsRate,
    ScraperConfig,
    BankScraper,
)


class TestPydanticModels:
    """Test pydantic model validation and parsing."""
    
    def test_savings_rate_valid(self):
        """Test creating a valid SavingsRate."""
        rate = SavingsRate(
            bank_name="Test Bank",
            product_name="1 Year Fixed",
            aer_rate=0.05,
            url="https://example.com"
        )
        assert rate.bank_name == "Test Bank"
        assert rate.aer_rate == 0.05
        assert isinstance(rate.scraped_at, datetime)
    
    def test_savings_rate_parse_percentage_string(self):
        """Test parsing AER rate from percentage string."""
        rate = SavingsRate(
            bank_name="Test Bank",
            product_name="1 Year Fixed",
            aer_rate="5.0%",
            url="https://example.com"
        )
        assert rate.aer_rate == 0.05
    
    def test_savings_rate_parse_decimal_string(self):
        """Test parsing AER rate from decimal string."""
        rate = SavingsRate(
            bank_name="Test Bank",
            product_name="1 Year Fixed",
            aer_rate="0.05",
            url="https://example.com"
        )
        assert rate.aer_rate == 0.05
    
    def test_savings_rate_parse_large_number(self):
        """Test parsing AER rate from large number (assumed percentage)."""
        rate = SavingsRate(
            bank_name="Test Bank",
            product_name="1 Year Fixed",
            aer_rate="5.5",
            url="https://example.com"
        )
        assert rate.aer_rate == 0.055
    
    def test_savings_rate_invalid_negative(self):
        """Test that negative rates are rejected."""
        with pytest.raises(ValueError):
            SavingsRate(
                bank_name="Test Bank",
                product_name="1 Year Fixed",
                aer_rate=-0.05,
                url="https://example.com"
            )
    
    def test_savings_rate_invalid_over_100_percent(self):
        """Test that rates over 100% are rejected."""
        with pytest.raises(ValueError):
            SavingsRate(
                bank_name="Test Bank",
                product_name="1 Year Fixed",
                aer_rate=1.5,
                url="https://example.com"
            )
    
    def test_bank_config_frozen(self):
        """Test that BankConfig is immutable."""
        selectors = BankSelectors(
            container=".product",
            product_name=".name",
            aer_rate=".rate"
        )
        bank = BankConfig(
            name="Test Bank",
            url="https://example.com",
            product_type="1 Year Fixed",
            selectors=selectors
        )
        
        with pytest.raises(Exception):  # pydantic will raise validation error
            bank.name = "New Name"


class TestScraperConfig:
    """Test configuration loading."""
    
    def test_load_from_yaml(self, tmp_path):
        """Test loading configuration from YAML file."""
        config_content = """
banks:
  - name: "Test Bank"
    url: "https://example.com"
    product_type: "1 Year Fixed"
    selectors:
      container: ".product"
      product_name: ".name"
      aer_rate: ".rate"
"""
        config_file = tmp_path / "test_config.yaml"
        config_file.write_text(config_content)
        
        config = ScraperConfig.from_yaml(config_file)
        
        assert len(config.banks) == 1
        assert config.banks[0].name == "Test Bank"
        assert config.banks[0].url == "https://example.com"
        assert config.banks[0].selectors.container == ".product"


class TestBankScraper:
    """Test web scraping functionality."""
    
    def test_extract_rate_from_text_percentage(self):
        """Test extracting rate from text with percentage sign."""
        config = ScraperConfig(banks=[])
        scraper = BankScraper(config)
        
        rate = scraper._extract_rate_from_text("AER: 5.25%")
        assert rate == 0.0525
    
    def test_extract_rate_from_text_decimal(self):
        """Test extracting rate from text with decimal."""
        config = ScraperConfig(banks=[])
        scraper = BankScraper(config)
        
        rate = scraper._extract_rate_from_text("Rate: 4.75")
        assert rate == 0.0475
    
    def test_extract_rate_from_text_no_match(self):
        """Test extracting rate from text with no rate."""
        config = ScraperConfig(banks=[])
        scraper = BankScraper(config)
        
        rate = scraper._extract_rate_from_text("No rate here")
        assert rate is None
    
    @patch('scraper.requests.Session.get')
    def test_scrape_bank_success(self, mock_get):
        """Test successful scraping of a bank."""
        html_content = """
        <html>
            <body>
                <div class="product">
                    <h3 class="name">1 Year Fixed Savings</h3>
                    <div class="rate">AER: 5.0%</div>
                </div>
            </body>
        </html>
        """
        
        mock_response = Mock()
        mock_response.content = html_content.encode('utf-8')
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        selectors = BankSelectors(
            container=".product",
            product_name=".name",
            aer_rate=".rate"
        )
        bank = BankConfig(
            name="Test Bank",
            url="https://example.com",
            product_type="1 Year Fixed",
            selectors=selectors
        )
        config = ScraperConfig(banks=[bank])
        scraper = BankScraper(config)
        
        rates = scraper.scrape_bank(bank)
        
        assert len(rates) == 1
        assert rates[0].bank_name == "Test Bank"
        assert rates[0].product_name == "1 Year Fixed Savings"
        assert rates[0].aer_rate == 0.05
    
    @patch('scraper.requests.Session.get')
    def test_scrape_bank_network_error(self, mock_get):
        """Test handling of network errors."""
        mock_get.side_effect = Exception("Network error")
        
        selectors = BankSelectors(
            container=".product",
            product_name=".name",
            aer_rate=".rate"
        )
        bank = BankConfig(
            name="Test Bank",
            url="https://example.com",
            product_type="1 Year Fixed",
            selectors=selectors
        )
        config = ScraperConfig(banks=[bank])
        scraper = BankScraper(config)
        
        rates = scraper.scrape_bank(bank)
        
        assert len(rates) == 0
    
    def test_save_to_parquet(self, tmp_path):
        """Test saving rates to parquet file."""
        rates = [
            SavingsRate(
                bank_name="Bank A",
                product_name="1 Year Fixed",
                aer_rate=0.05,
                url="https://example.com/a"
            ),
            SavingsRate(
                bank_name="Bank B",
                product_name="1 Year Fixed",
                aer_rate=0.055,
                url="https://example.com/b"
            ),
        ]
        
        output_path = tmp_path / "test_rates.parquet"
        config = ScraperConfig(banks=[])
        scraper = BankScraper(config)
        
        scraper.save_to_parquet(rates, output_path)
        
        # Verify file was created and can be read
        assert output_path.exists()
        df = pd.read_parquet(output_path)
        assert len(df) == 2
        assert df['bank_name'].tolist() == ["Bank A", "Bank B"]
        assert df['aer_rate'].tolist() == [0.05, 0.055]
        assert 'aer_rate_percent' in df.columns


class TestSecureTrustBank:
    """Specific tests for Secure Trust Bank scraping."""
    
    @patch('scraper.requests.Session.get')
    def test_secure_trust_bank_scraping(self, mock_get):
        """
        Test scraping Secure Trust Bank website.
        
        This test uses a mock HTML response that simulates the structure
        of the Secure Trust Bank website.
        """
        # Mock HTML content simulating Secure Trust Bank website structure
        html_content = """
        <html>
            <head><title>Secure Trust Bank Savings</title></head>
            <body>
                <div class="savings-products">
                    <div class="product-card">
                        <h3 class="product-title">Easy Access Savings</h3>
                        <div class="rate-info">
                            <span class="aer-rate">3.5%</span>
                            <span class="label">AER</span>
                        </div>
                    </div>
                    <div class="product-card">
                        <h3 class="product-title">1 Year Fixed Rate Savings</h3>
                        <div class="rate-info">
                            <span class="aer-rate">5.25%</span>
                            <span class="label">AER</span>
                        </div>
                        <p class="product-description">Lock in your savings for 1 year</p>
                    </div>
                    <div class="product-card">
                        <h3 class="product-title">2 Year Fixed Rate Savings</h3>
                        <div class="rate-info">
                            <span class="aer-rate">5.50%</span>
                            <span class="label">AER</span>
                        </div>
                    </div>
                </div>
            </body>
        </html>
        """
        
        mock_response = Mock()
        mock_response.content = html_content.encode('utf-8')
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        # Create Secure Trust Bank configuration
        selectors = BankSelectors(
            container=".product-card",
            product_name=".product-title",
            aer_rate=".aer-rate"
        )
        bank = BankConfig(
            name="Secure Trust Bank",
            url="https://www.securetrustbank.com/savings",
            product_type="1 Year Fixed",
            selectors=selectors
        )
        config = ScraperConfig(banks=[bank])
        scraper = BankScraper(config)
        
        # Scrape the bank
        rates = scraper.scrape_bank(bank)
        
        # Assertions
        assert len(rates) == 1, "Should find exactly one 1 Year Fixed product"
        
        rate = rates[0]
        assert rate.bank_name == "Secure Trust Bank"
        assert "1 Year" in rate.product_name
        assert "Fixed" in rate.product_name
        assert rate.aer_rate == 0.0525  # 5.25%
        assert rate.url == "https://www.securetrustbank.com/savings"
        assert isinstance(rate.scraped_at, datetime)
    
    @patch('scraper.requests.Session.get')
    def test_secure_trust_bank_alternative_structure(self, mock_get):
        """
        Test Secure Trust Bank with alternative HTML structure.
        
        This tests the scraper's ability to handle variations in HTML structure.
        """
        html_content = """
        <html>
            <body>
                <div class="rate-table">
                    <div class="savings-product">
                        <h4>Fixed Rate Savings - 1 Year</h4>
                        <div class="interest-rate">AER 5.10%</div>
                    </div>
                </div>
            </body>
        </html>
        """
        
        mock_response = Mock()
        mock_response.content = html_content.encode('utf-8')
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        # Update selectors to match alternative structure
        selectors = BankSelectors(
            container=".savings-product, .product-card, .rate-table",
            product_name=".product-title, h3, h4",
            aer_rate=".aer-rate, .rate, .interest-rate"
        )
        bank = BankConfig(
            name="Secure Trust Bank",
            url="https://www.securetrustbank.com/savings",
            product_type="1 Year",
            selectors=selectors
        )
        config = ScraperConfig(banks=[bank])
        scraper = BankScraper(config)
        
        rates = scraper.scrape_bank(bank)
        
        assert len(rates) >= 1
        # Check that we found a 1 Year product
        assert any("1 Year" in r.product_name or "1 year" in r.product_name.lower() for r in rates)


class TestEndToEnd:
    """End-to-end integration tests."""
    
    @patch('scraper.requests.Session.get')
    def test_full_scraping_workflow(self, mock_get, tmp_path):
        """Test the complete workflow: config -> scrape -> save."""
        # Create config file
        config_content = """
banks:
  - name: "Mock Bank"
    url: "https://mockbank.com"
    product_type: "1 Year Fixed"
    selectors:
      container: ".product"
      product_name: ".name"
      aer_rate: ".rate"
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)
        
        # Mock HTML response
        html_content = """
        <html>
            <body>
                <div class="product">
                    <div class="name">1 Year Fixed Savings Account</div>
                    <div class="rate">4.8% AER</div>
                </div>
            </body>
        </html>
        """
        
        mock_response = Mock()
        mock_response.content = html_content.encode('utf-8')
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        # Load config and scrape
        config = ScraperConfig.from_yaml(config_file)
        scraper = BankScraper(config)
        rates = scraper.scrape_all()
        
        # Save to parquet
        output_file = tmp_path / "rates.parquet"
        scraper.save_to_parquet(rates, output_file)
        
        # Verify
        assert len(rates) == 1
        assert output_file.exists()
        
        df = pd.read_parquet(output_file)
        assert len(df) == 1
        assert df.iloc[0]['bank_name'] == "Mock Bank"
        assert df.iloc[0]['aer_rate'] == 0.048


if __name__ == "__main__":
    # Execute tests when run directly
    import sys
    import pytest
    
    sys.exit(pytest.main([__file__, "-v"]))
