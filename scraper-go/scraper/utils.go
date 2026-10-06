package scraper

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"strings"
	"time"

	"github.com/PuerkitoBio/goquery"
	"github.com/chromedp/chromedp"
	"go.mongodb.org/mongo-driver/bson"
)

const naivasBase = "https://naivas.online"

// ---------- small helpers ----------

func absURL(link string) string {
	if strings.HasPrefix(link, "/") {
		return naivasBase + link
	}
	return link
}

func docFromHTML(html string) (*goquery.Document, error) {
	return goquery.NewDocumentFromReader(strings.NewReader(html))
}

// firstText returns the trimmed text of the first selector that matches non-empty text.
func firstText(doc *goquery.Document, selectors ...string) string {
	for _, sel := range selectors {
		txt := strings.TrimSpace(doc.Find(sel).First().Text())
		if txt != "" {
			return txt
		}
	}
	return ""
}

// parsePriceText pulls the first number out of text like "KES 1,299.00" -> "1299.00".
func parsePriceText(s string) string {
	var b strings.Builder
	started := false
	for _, r := range s {
		switch {
		case r >= '0' && r <= '9':
			started = true
			b.WriteRune(r)
		case r == '.' && started:
			b.WriteRune(r)
		case r == ',' && started:
			// thousands separator, skip
		default:
			if started {
				return strings.TrimRight(b.String(), ".")
			}
		}
	}
	return strings.TrimRight(b.String(), ".")
}

func ldString(m map[string]interface{}, key string) string {
	if v, ok := m[key].(string); ok {
		return strings.TrimSpace(v)
	}
	return ""
}

func ldOffer(m map[string]interface{}) map[string]interface{} {
	switch o := m["offers"].(type) {
	case map[string]interface{}:
		return o
	case []interface{}:
		if len(o) > 0 {
			if first, ok := o[0].(map[string]interface{}); ok {
				return first
			}
		}
	}
	return nil
}

func buildNaivasProduct(name, price string, promo bool, promoDetails, productURL, category string) *bson.M {
	now := time.Now()
	return &bson.M{
		"product_name":      strings.TrimSpace(name),
		"store_chain":       "Naivas",
		"store_branch":      "Online Store",
		"price_kes":         price,
		"currency":          "KES",
		"source":            "naivas_online",
		"is_promotional":    promo,
		"promotion_details": promoDetails,
		"category":          category,
		"response_url":      productURL,
		"verified_at":       now,
		"created_at":        now,
		"scraper":           "go",
	}
}

// ---------- category links ----------

// extractNaivasCategoryLinks extracts category links from the homepage HTML.
func extractNaivasCategoryLinks(html string) []string {
	doc, err := docFromHTML(html)
	if err != nil {
		log.Printf("Error parsing homepage HTML: %v", err)
		return nil
	}

	seen := make(map[string]bool)
	var links []string
	doc.Find(`#mega-menu-full a[href]`).Each(func(_ int, s *goquery.Selection) {
		href, _ := s.Attr("href")
		link := absURL(strings.TrimSpace(href))
		if strings.HasPrefix(link, "http") && strings.Contains(link, "/category/") && !seen[link] {
			seen[link] = true
			links = append(links, link)
		}
	})
	return links
}

// extractCategoryFromURL tries to extract a category name from a URL.
// Example: https://naivas.online/category/dairy-eggs -> "Dairy Eggs"
func extractCategoryFromURL(url string) string {
	if idx := strings.LastIndex(url, "/category/"); idx != -1 {
		category := url[idx+len("/category/"):]
		if end := strings.IndexAny(category, "/?"); end != -1 {
			category = category[:end]
		}
		category = strings.ReplaceAll(category, "-", " ")
		return strings.Title(category)
	}
	return "General"
}

// ---------- category scraping ----------

// scrapeNaivasCategory scrapes a category (with pagination) and returns products.
// parent must be a chromedp context (from chromedp.NewContext), typed as context.Context.
func scrapeNaivasCategory(parent context.Context, categoryURL string, category string, town string, branch string) []bson.M {
	var products []bson.M

	taskCtx, cancel := chromedp.NewContext(parent)
	defer cancel()

	currentURL := categoryURL
	pageNum := 1

	for currentURL != "" {
		log.Printf("Scraping Naivas category page %d: %s", pageNum, currentURL)

		var pageHTML string
		err := chromedp.Run(taskCtx,
			chromedp.Navigate(currentURL),
			chromedp.WaitReady("body"),
			chromedp.OuterHTML(`html`, &pageHTML),
		)
		if err != nil {
			log.Printf("Failed to fetch Naivas category page %s: %v", currentURL, err)
			break
		}

		productLinks := extractNaivasProductLinks(pageHTML)
		log.Printf("Found %d product links on page %d", len(productLinks), pageNum)

		for _, productLink := range productLinks {
			product := extractNaivasProductDetails(parent, productLink, category)
			if product != nil {
				products = append(products, *product)
			}
			time.Sleep(300 * time.Millisecond)
		}

		nextURL := extractNaivasNextPageLink(pageHTML)
		if nextURL == "" || nextURL == currentURL {
			break
		}
		currentURL = nextURL
		pageNum++
		time.Sleep(2 * time.Second)
	}

	return products
}

// extractNaivasProductLinks extracts product links from a category page.
func extractNaivasProductLinks(html string) []string {
	doc, err := docFromHTML(html)
	if err != nil {
		log.Printf("Error parsing category HTML: %v", err)
		return nil
	}

	seen := make(map[string]bool)
	var links []string
	doc.Find(`.product-img a[href]`).Each(func(_ int, s *goquery.Selection) {
		href, _ := s.Attr("href")
		link := absURL(strings.TrimSpace(href))
		if (strings.Contains(link, "/product/") || strings.Contains(link, "/products/")) && !seen[link] {
			seen[link] = true
			links = append(links, link)
		}
	})
	return links
}

// extractNaivasNextPageLink extracts the next-page link from a category page.
func extractNaivasNextPageLink(html string) string {
	doc, err := docFromHTML(html)
	if err != nil {
		return ""
	}
	sel := doc.Find(`a[rel="next"], a.next-page, .next-page a, a.pagination__next, .pagination__next a`).First()
	href, ok := sel.Attr("href")
	if !ok {
		return ""
	}
	return absURL(strings.TrimSpace(href))
}

// ---------- product details ----------

// extractNaivasProductDetails loads a product page and extracts its data.
func extractNaivasProductDetails(parent context.Context, productURL string, category string) *bson.M {
	taskCtx, cancel := chromedp.NewContext(parent)
	defer cancel()
	timeoutCtx, cancelTimeout := context.WithTimeout(taskCtx, 20*time.Second)
	defer cancelTimeout()

	var html string
	err := chromedp.Run(timeoutCtx,
		chromedp.Navigate(productURL),
		chromedp.WaitReady("body"),
		chromedp.OuterHTML(`html`, &html),
	)
	if err != nil {
		log.Printf("Failed to fetch product page %s: %v", productURL, err)
		return nil
	}

	doc, err := docFromHTML(html)
	if err != nil {
		log.Printf("Failed to parse product page %s: %v", productURL, err)
		return nil
	}

	if product := extractNaivasFromJSONLD(doc, productURL, category); product != nil {
		return product
	}
	return extractNaivasFromCSS(doc, productURL, category)
}

// extractNaivasFromJSONLD parses product data from JSON-LD <script> tags.
func extractNaivasFromJSONLD(doc *goquery.Document, productURL string, category string) *bson.M {
	var result *bson.M

	doc.Find(`script[type="application/ld+json"]`).EachWithBreak(func(_ int, s *goquery.Selection) bool {
		var data interface{}
		if err := json.Unmarshal([]byte(s.Text()), &data); err != nil {
			return true // keep looking
		}

		var items []interface{}
		switch v := data.(type) {
		case []interface{}:
			items = v
		case map[string]interface{}:
			items = []interface{}{v}
		default:
			return true
		}

		for _, item := range items {
			m, ok := item.(map[string]interface{})
			if !ok || !strings.Contains(fmt.Sprint(m["@type"]), "Product") {
				continue
			}

			name := ldString(m, "name")
			if name == "" {
				continue
			}

			offer := ldOffer(m)
			if offer == nil {
				continue
			}
			price := ""
			switch v := offer["price"].(type) {
			case string:
				price = parsePriceText(v)
			case float64:
				price = fmt.Sprintf("%.2f", v)
			}
			if price == "" {
				continue
			}

			// JSON-LD doesn't reliably indicate promotions; CSS path handles was/now pricing.
			result = buildNaivasProduct(name, price, false, "", productURL, category)
			return false // stop searching
		}
		return true
	})

	return result
}

// extractNaivasFromCSS extracts product details with CSS selectors (fallback).
func extractNaivasFromCSS(doc *goquery.Document, productURL string, category string) *bson.M {
	productName := firstText(doc,
		`h1[data-testid="product-title"]`,
		`[data-testid="product-title"]`,
		`.product-title`,
		`.product-name`,
		`h1`,
	)
	priceText := firstText(doc,
		`[data-testid="price"]`,
		`.price-current`,
		`.price-sale`,
		`.price`,
		`[class*="price"]`,
		`.cost`,
	)

	if productName == "" || priceText == "" {
		log.Printf("Could not extract product name or price from %s", productURL)
		return nil
	}

	isPromotional := false
	promotionDetails := ""

	if promo := firstText(doc,
		`.badge-sale`,
		`.label-offer`,
		`.promo-tag`,
		`[data-testid="price-original"]`,
		`.price-was`,
		`.original-price`,
	); promo != "" {
		isPromotional = true
		promotionDetails = promo
	}

	if !isPromotional {
		wasPrice := firstText(doc, `.price-was`)
		nowPrice := firstText(doc, `.price-current`)
		if wasPrice != "" && nowPrice != "" {
			isPromotional = true
			promotionDetails = fmt.Sprintf("Was %s, now %s", wasPrice, nowPrice)
		}
	}

	price := parsePriceText(priceText)
	if price == "" {
		log.Printf("Could not parse price %q from %s", priceText, productURL)
		return nil
	}

	return buildNaivasProduct(productName, price, isPromotional, promotionDetails, productURL, category)
}