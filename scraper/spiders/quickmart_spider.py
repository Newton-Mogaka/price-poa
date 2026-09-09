"""
Scrapy spider for scraping prices from Quickmart Kenya Online.
"""
import scrapy
import re
from scrapy.http import Response
from typing import Generator, Dict, Any, Optional
import logging
from scraper.base_spider import BasePricePoaSpider
from scraper.config.quickmart_branches import resolve_branch

logger = logging.getLogger(__name__)


class QuickmartSpider(BasePricePoaSpider):
    """Spider for scraping Quickmart Kenya Online store."""
    
    name = 'quickmart_spider'
    allowed_domains = ['quickmart.co.ke']
    start_urls = [
        'https://www.quickmart.co.ke/',
    ]

    # Domains that require JavaScript rendering
    js_domains = ['quickmart.co.ke']

    custom_settings = {
        'RETRY_TIMES': 2,
        'USER_AGENT': 'PricePoa Scraper - Quickmart (+https://pricepoa.co.ke)',
    }

    def __init__(self, town: Optional[str] = None, branch: Optional[str] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.store_chain = "Quickmart"
        
        # Resolve branch profile based on passed town or branch name
        branch_profile = resolve_branch(town=town, branch=branch)
        self.default_store_branch = branch_profile["branch_name"]
        self.branch_town = branch_profile["town"]
        self.branch_county = branch_profile["county"]
        self.branch_lat = branch_profile.get("gps_latitude")
        self.branch_lng = branch_profile.get("gps_longitude")
        self.branch_address = branch_profile.get("address")
        self.location_gate_cookies = branch_profile["cookies"]
        
        logger.info(
            f"QuickmartSpider initialized for branch '{self.default_store_branch}' "
            f"in {self.branch_town}, {self.branch_county} (Shop ID: {branch_profile['shop_id']})"
        )

    def parse(self, response: Response) -> Generator[scrapy.Request, None, None]:
        """Parse Quickmart homepage and extract category links."""
        logger.info(f"Parsing Quickmart homepage: {response.url} for branch {self.default_store_branch}")

        category_links = response.css(
            '.category-menu-link.categoryMenuLinkJs::attr(href)'
        ).getall()

        branch_meta = {
            'store_branch': self.default_store_branch,
            'store_town': self.branch_town,
            'store_county': self.branch_county,
            'gps_latitude': self.branch_lat,
            'gps_longitude': self.branch_lng,
            'store_address': self.branch_address,
        }

        for link in set(category_links):
            # Skip the "all categories" toggle link, which isn't a real category page
            if link and 'btn-all-categories' not in link:
                meta = {'use_playwright': self._needs_js(link), **branch_meta}
                yield response.follow(
                    url=link,
                    callback=self.parse_category,
                    meta=meta
                )

    def parse_category(self, response: Response) -> Generator[scrapy.Request, None, None]:
        """Parse category page and extract product links."""
        logger.info(f"Parsing Quickmart category: {response.url}")

        # a.products-title is the real product link (an <a> tag). The shop-branch
        # selector widget on the homepage reuses .products.product-item styling but
        # renders its title as a plain <h3>, never an <a>, so this selector naturally
        # excludes that false-positive without needing extra filtering.
        product_links = response.css(
            'a.products-title::attr(href)'
        ).getall()

        for link in set(product_links):
            if link:
                meta = {
                    'use_playwright': self._needs_js(link),
                    'store_branch': response.meta.get('store_branch', self.default_store_branch),
                    'store_town': response.meta.get('store_town', self.branch_town),
                    'store_county': response.meta.get('store_county', self.branch_county),
                    'gps_latitude': response.meta.get('gps_latitude', self.branch_lat),
                    'gps_longitude': response.meta.get('gps_longitude', self.branch_lng),
                    'store_address': response.meta.get('store_address', self.branch_address),
                    'category': response.meta.get('category', 'General'),
                }
                yield response.follow(
                    url=link,
                    callback=self.parse_product,
                    meta=meta
                )

        # Handle pagination
        next_page = response.css(
            'a[rel="next"]::attr(href), .next-page::attr(href), .pagination__next::attr(href)'
        ).get()
        if next_page:
            yield response.follow(
                url=next_page,
                callback=self.parse_category,
                meta=response.meta
            )

    def parse_product(self, response: Response) -> Generator[Dict[str, Any], None, None]:
        """Parse individual product page and extract details."""
        logger.info(f"Parsing Quickmart product: {response.url}")

        branch_fields = {
            'store_branch': response.meta.get('store_branch', self.default_store_branch),
            'store_town': response.meta.get('store_town', self.branch_town),
            'store_county': response.meta.get('store_county', self.branch_county),
            'gps_latitude': response.meta.get('gps_latitude', self.branch_lat),
            'gps_longitude': response.meta.get('gps_longitude', self.branch_lng),
            'store_address': response.meta.get('store_address', self.branch_address),
        }

        # 1. Try to parse from JSON-LD schema first (most reliable for Next.js/E-commerce apps)
        try:
            for script in response.xpath('//script[@type="application/ld+json"]/text()').getall():
                import json
                try:
                    data = json.loads(script)
                    data_list = data if isinstance(data, list) else [data]
                    for item in data_list:
                        if item.get('@type') == 'Product':
                            name = item.get('name')
                            offers = item.get('offers', {})
                            price = offers.get('price')
                            if name and price:
                                yield self.build_item(
                                    product_name=name.strip(),
                                    price_kes=str(price),
                                    source='quickmart_online',
                                    response_url=response.url,
                                    category=response.meta.get('category', 'General'),
                                    **branch_fields
                                )
                                return
                except Exception as e:
                    logger.debug(f"JSON-LD parsing block error: {e}")
        except Exception as e:
            logger.warning(f"Error checking JSON-LD: {e}")

        # 2. Fallback to CSS selectors if JSON-LD was missing or failed
        try:
            product_name = self._extract_first(response, [
                'h1.product-title *::text',
                'h1.product-title::text',
                '.product-title *::text',
                '.product-title::text',
                'h1 *::text',
                'h1::text',
                '.product-name *::text',
                '.product-name::text',
            ])

            category = self._extract_first(response, [
                '.breadcrumb li:last-child a::text',
                '.breadcrumb li:last-child::text',
                '.category-path::text'
            ]) or response.meta.get('category', 'General')

            price_text = self._extract_first(response, [
                '.products-price-new *::text',
                '.products-price-new::text',
                '.products-price *::text',
                '.price-new *::text',
                '.price-new::text',
                '.product-price *::text',
                '.price::text',
                '.current-price::text',
                '[data-testid="price"]::text',
                '.sale-price::text',
            ])

            if not product_name or not price_text:
                logger.warning(f"Missing product name or price for {response.url} (found name={repr(product_name)}, price={repr(price_text)})")
                return

            # Check for promotional details
            promo_selector = self._extract_first(response, [
                '.products-price-old *::text',
                '.products-price-off *::text',
                '.badge-offer, .label-sale, .promo-badge',
                '[data-testid="original-price"]',
                '.was-price::text'
            ])
            is_promotional = bool(promo_selector)

            promotion_details = None
            if is_promotional:
                was_price = self._extract_first(response, ['.products-price-old *::text', '.products-price-old::text'])
                discount = self._extract_first(response, ['.products-price-off *::text', '.products-price-off::text'])
                if was_price:
                    was_price = re.sub(r'\s+', ' ', was_price).strip()
                if discount:
                    discount = re.sub(r'\s+', ' ', discount).strip()
                if was_price and discount:
                    promotion_details = f"Was {was_price} ({discount})"
                elif was_price:
                    promotion_details = f"Was {was_price}"
                else:
                    raw_promo = self._extract_first(response, [
                        '.offer-details::text',
                        '.promo-text::text',
                        '.badge-offer::text'
                    ])
                    promotion_details = re.sub(r'\s+', ' ', raw_promo).strip() if raw_promo else None

            numeric_price = self._clean_price(price_text)

            yield self.build_item(
                product_name=product_name,
                price_kes=numeric_price if numeric_price is not None else price_text,
                source='quickmart_online',
                is_promotional=is_promotional,
                promotion_details=promotion_details,
                response_url=response.url,
                category=category,
                **branch_fields
            )

        except Exception as e:
            logger.error(f"Error parsing Quickmart product {response.url}: {e}", exc_info=True)

    def _clean_price(self, price_val: Optional[str]) -> Optional[float]:
        """Convert a raw price string like 'KES 1,399.00' to float."""
        if not price_val:
            return None
        val_str = str(price_val).replace(',', '').strip()
        match = re.search(r'\d+(?:\.\d+)?', val_str)
        if match:
            try:
                return float(match.group(0))
            except (ValueError, TypeError):
                return None
        return None

    def _extract_first(self, response: Response, selectors: list) -> Optional[str]:
        """Extract trimmed non-empty text from the first selector that yields a match."""
        for selector in selectors:
            for val in response.css(selector).getall():
                cleaned = val.strip()
                if cleaned:
                    return cleaned
        return None