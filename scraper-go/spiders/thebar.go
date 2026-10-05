package spiders

import (
	"context"
	"fmt"
	"log"
	"strings"
	"time"

	"github.com/chromedp/chromedp"
	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"

	"github.com/pricepoa/scraper-go/scraper"
)

// RunTheBarSpider runs the The Bar spider
func RunTheBarSpider(ctx context.Context, pricesColl *mongo.Collection, town string, branch string) {
	// The Bar spider doesn't use town/branch, but we accept the params for consistency
	log.Println("Running The Bar spider")

	// Create chromedp context for JS rendering
	chromeCtx, cancel := chromedp.NewContext(ctx)
	defer cancel()

	var products []bson.M

	// Navigate to collections page and extract product links
	var collectionsHTML string
	err := chromedp.Run(chromeCtx,
		chromedp.Navigate(`https://ke.thebar.com/collections/party`),
		chromedp.OuterHTML(`html`, &collectionsHTML),
	)
	if err != nil {
		log.Printf("Failed to fetch The Bar collections page: %v", err)
		return
	}

	// Parse product links from collections page
	productLinks := extractProductLinks(collectionsHTML)
	log.Printf("Found %d product links on The Bar collections page", len(productLinks))

	// Limit for testing if needed (remove in production)
	// if len(productLinks) > 10 {
	// 	productLinks = productLinks[:10]
	// }

	// Process each product link
	for _, link := range productLinks {
		product := extractProductDetails(chromeCtx, link)
		if product != nil {
			products = append(products, *product)
		}
		// Be respectful - small delay between requests
		time.Sleep(500 * time.Millisecond)
	}

	if len(products) == 0 {
		log.Println("No products extracted from The Bar")
		return
	}

	// Insert all products
	if len(products) > 0 {
		var docs []interface{}
		for _, p := range products {
			docs = append(docs, p)
		}

		insertManyOpts := options.InsertMany().SetOrdered(false)
		result, err := pricesColl.InsertMany(ctx, docs, insertManyOpts)
		if err != nil {
			log.Printf("Failed to insert products: %v", err)
			return
		}
		log.Printf("Inserted %d products from The Bar", len(result.InsertedIDs))
	}
}

// extractProductLinks extracts product links from the collections page HTML
func extractProductLinks(html string) []string {
	var links []string

	// Use chromedp to extract links from HTML string
	ctx, cancel := chromedp.NewContext(context.Background())
	defer cancel()

	var nodes []*chromedp.Node
	err := chromedp.Run(ctx,
		chromedp.HTML(`<html><body>`+html+`</body></html>`, &nodes),
		chromedp.Nodes(`a[href*="/products/"]`, &nodes, chromedp.ByQueryAll),
	)
	if err != nil {
		log.Printf("Error extracting product links with chromedp: %v", err)
		return extractProductLinksFallback(html)
	}

	for _, node := range nodes {
		for _, attr := range node.Attributes {
			if attr.Key == "href" {
				link := attr.Val
				// Make absolute if relative
				if strings.HasPrefix(link, "/") {
					link = "https://ke.thebar.com" + link
				}
				// Filter for product links
				if strings.Contains(link, "/products/") {
					links = append(links, link)
				}
				break
			}
		}
	}

	// Deduplicate
	seen := make(map[string]bool)
	var uniqueLinks []string
	for _, link := range links {
		if !seen[link] {
			seen[link] = true
			uniqueLinks = append(uniqueLinks, link)
		}
	}
	return uniqueLinks
}

// Fallback product link extraction
func extractProductLinksFallback(html string) []string {
	var links []string
	// Simple extraction of href from a[href*="/products/"]
	start := 0
	for {
		startIdx := strings.Index(html[start:], `a[href*="/products/"]`)
		if startIdx == -1 {
			break
		}
		start += startIdx
		// Look for href attribute
		hrefIdx := strings.Index(html[start:], `href="`)
		if hrefIdx == -1 {
			start++
			continue
		}
		start += hrefIdx + 6 // skip 'href="'
		endIdx := strings.Index(html[start:], `"`)
		if endIdx == -1 {
			start++
			continue
		}
		link := html[start : start+endIdx]
		start += endIdx

		// Make absolute if relative
		if strings.HasPrefix(link, "/") {
			link = "https://ke.thebar.com" + link
		}
		// Filter for product links
		if strings.Contains(link, "/products/") {
			links = append(links, link)
		}
	}
	return links
}

// extractProductDetails navigates to a product URL and extracts product information
func extractProductDetails(chromeCtx *chromedp.Context, productURL string) *bson.M {
	// Create a task context with timeout
	taskCtx, cancel := chromedp.NewContext(chromeCtx)
	defer cancel()
	taskCtx, cancel = context.WithTimeout(taskCtx, 20*time.Second)
	defer cancel()

	var html string
	err := chromedp.Run(taskCtx,
		chromedp.Navigate(productURL),
		chromedp.OuterHTML(`html`, &html),
	)
	if err != nil {
		log.Printf("Failed to fetch product page %s: %v", productURL, err)
		return nil
	}

	// Try to extract from JSON-LD first
	product := extractFromJSONLD(html, productURL)
	if product != nil {
		return product
	}

	// Fallback to CSS selectors
	return extractFromCSS(html, productURL)
}

// extractFromJSONLD tries to parse product data from JSON-LD scripts
func extractFromJSONLD(html string, productURL string) *bson.M {
	// Find all application/ld+json scripts
	var scripts []string
	ctx, cancel := chromedp.NewContext(context.Background())
	defer cancel()

	err := chromedp.Run(ctx,
		chromedp.HTML(`<html><body>`+html+`</body></html>`, &scripts),
		chromedp.Nodes(`script[type="application/ld+json"]`, &scripts, chromedp.ByQueryAll),
	)
	if err != nil {
		// Fallback to simple extraction
		return extractFromJSONLDFallback(html, productURL)
	}

	for _, script := range scripts {
		var data interface{}
		if err := json.Unmarshal([]byte(script), &data); err != nil {
			continue
		}

		// Handle both single object and array
		var items []interface{}
		switch v := data.(type) {
		case []interface{}:
			items = v
		case map[string]interface{}:
			items = []interface{}{v}
		default:
			continue
		}

		for _, item := range items {
			itemMap, ok := item.(map[string]interface{})
			if !ok {
				continue
			}
			if itemMap["@type"] == "Product" || (itemMap["@type"] != nil && strings.Contains(fmt.Sprint(itemMap["@type"]), "Product")) {
				// Extract product details
				name := scraper.extractString(itemMap, "name")
				if name == "" {
					continue
				}

				price := ""
				if offers, ok := itemMap["offers"].(map[string]interface{}); ok {
					if priceVal, ok := offers["price"]; ok {
						switch v := priceVal.(type) {
						case string:
							price = v
						case float64:
							price = fmt.Sprintf("%.2f", v)
						}
					}
				}
				if price == "" {
					continue
				}

				// Check for promotional details
				isPromotional := false
				var promotionDetails string
				if priceOriginal, ok := itemMap["offers"].(map[string]interface{})["priceSpecification"].(map[string]interface{})["price"]; ok {
					// This is simplified - actual promotion detection would be more complex
					isPromotional = true
				}

				// Build product document
				return &bson.M{
					"product_name":   strings.TrimSpace(name),
					"store_chain":    "The Bar",
					"store_branch":   "Online Store",
					"price_kes":      price,
					"currency":       "KES",
					"source":         "thebar_online",
					"is_promotional": isPromotional,
					"promotion_details": promotionDetails,
					"category":       "Party", // As requested, save under Party category
					"response_url":   productURL,
					"verified_at":    time.Now(),
					"created_at":     time.Now(),
					"scraper":        "go",
				}
			}
		}
	}
	return nil
}

// Fallback JSON-LD extraction
func extractFromJSONLDFallback(html string, productURL string) *bson.M {
	// Simple extraction of JSON-LD content
	start := 0
	for {
		startIdx := strings.Index(html[start:], `<script type="application/ld+json">`)
		if startIdx == -1 {
			break
		}
		start += startIdx + len(`<script type="application/ld+json">`)
		endIdx := strings.Index(html[start:], `</script>`)
		if endIdx == -1 {
			break
		}
		script := html[start : start+endIdx]
		start += endIdx

		var data interface{}
		if err := json.Unmarshal([]byte(script), &data); err != nil {
			continue
		}

		// Process as above...
		var items []interface{}
		switch v := data.(type) {
		case []interface{}:
			items = v
		case map[string]interface{}:
			items = []interface{}{v}
		default:
			continue
		}

		for _, item := range items {
			itemMap, ok := item.(map[string]interface{})
			if !ok {
				continue
			}
			if itemMap["@type"] == "Product" || (itemMap["@type"] != nil && strings.Contains(fmt.Sprint(itemMap["@type"]), "Product")) {
				name := scraper.extractString(itemMap, "name")
				if name == "" {
					continue
				}

				price := ""
				if offers, ok := itemMap["offers"].(map[string]interface{}); ok {
					if priceVal, ok := offers["price"]; ok {
						switch v := priceVal.(type) {
						case string:
							price = v
						case float64:
							price = fmt.Sprintf("%.2f", v)
						}
					}
				}
				if price == "" {
					continue
				}

				// Check for promotional details (simplified)
				isPromotional := false
				var promotionDetails string

				return &bson.M{
					"product_name":   strings.TrimSpace(name),
					"store_chain":    "The Bar",
					"store_branch":   "Online Store",
					"price_kes":      price,
					"currency":       "KES",
					"source":         "thebar_online",
					"is_promotional": isPromotional,
					"promotion_details": promotionDetails,
					"category":       "Party", // As requested, save under Party category
					"response_url":   productURL,
					"verified_at":    time.Now(),
					"created_at":     time.Now(),
					"scraper":        "go",
				}
			}
		}
	}
	return nil
}

// extractFromCSS extracts product details using CSS selectors (fallback)
func extractFromCSS(html string, productURL string) *bson.M {
	ctx, cancel := chromedp.NewContext(context.Background())
	defer cancel()

	var productName string
	var priceText string
	var isPromotional bool
	var promotionDetails string

	// Try to extract product name
	nameSelectors := []string{
		`h1`,
		`.product-title`,
		`.product-name`,
		`h1[data-testid="product-title"]`,
		`[data-testid="product-title"]`,
	}
	for _, selector := range nameSelectors {
		err := chromedp.Run(ctx,
			chromedp.HTML(`<html><body>`+html+`</body></html>`, &productName),
			chromedp.Text(selector, &productName, chromedp.ByQuery),
		)
		if err == nil && strings.TrimSpace(productName) != "" {
			break
		}
	}

	// Try to extract price
	priceSelectors := []string{
		`[data-testid="price"]`,
		`.price-current`,
		`.sales-price`,
		`.price`,
		`[class*="price"]`,
		`.cost`,
	}
	for _, selector := range priceSelectors {
		err := chromedp.Run(ctx,
			chromedp.HTML(`<html><body>`+html+`</body></html>`, &priceText),
			chromedp.Text(selector, &priceText, chromedp.ByQuery),
		)
		if err == nil && strings.TrimSpace(priceText) != "" {
			break
		}
	}

	// Check for promotional details
	promoSelectors := []string{
		`.badge-sale`,
		`.label-offer`,
		`.promo-tag`,
		`[data-testid="price-original"]`,
		`.was-price`,
		`.original-price`,
	}
	for _, selector := range promoSelectors {
		var promoText string
		err := chromedp.Run(ctx,
			chromedp.HTML(`<html><body>`+html+`</body></html>`, &promoText),
			chromedp.Text(selector, &promoText, chromedp.ByQuery),
		)
		if err == nil && strings.TrimSpace(promoText) != "" {
			isPromotional = true
			promotionDetails = strings.TrimSpace(promoText)
			break
		}
	}

	// If we didn't find a specific promotion detail, check for was/now pricing
	if !isPromotional {
		var wasPrice string
		var nowPrice string
		err := chromedp.Run(ctx,
			chromedp.HTML(`<html><body>`+html+`</body></html>`, &wasPrice),
			chromedp.Text(`.was-price`, &wasPrice, chromedp.ByQuery),
		)
		if err == nil && strings.TrimSpace(wasPrice) != "" {
			err2 := chromedp.Run(ctx,
				chromedp.HTML(`<html><body>`+html+`</body></html>`, &nowPrice),
				chromedp.Text(`.price-current`, &nowPrice, chromedp.ByQuery),
			)
			if err2 == nil && strings.TrimSpace(nowPrice) != "" {
				// Simple check: if now price is less than was price, it's promotional
				// In a real implementation, we'd parse the numbers properly
				if strings.TrimSpace(nowPrice) != "" && strings.TrimSpace(wasPrice) != "" {
					isPromotional = true
					promotionDetails = fmt.Sprintf("Was %s, now %s", wasPrice, nowPrice)
				}
			}
		}
	}

	if strings.TrimSpace(productName) == "" || strings.TrimSpace(priceText) == "" {
		log.Printf("Could not extract product name or price from %s", productURL)
		return nil
	}

	// Clean price text (remove currency symbols, etc.)
	price := scraper.cleanPrice(priceText)

	return &bson.M{
		"product_name":   strings.TrimSpace(productName),
		"store_chain":    "The Bar",
		"store_branch":   "Online Store",
		"price_kes":      price,
		"currency":       "KES",
		"source":         "thebar_online",
		"is_promotional": isPromotional,
		"promotion_details": promotionDetails,
		"category":       "Party", // As requested, save under Party category
		"response_url":   productURL,
		"verified_at":    time.Now(),
		"created_at":     time.Now(),
		"scraper":        "go",
	}
}