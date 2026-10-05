package spiders

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"strings"
	"time"

	"github.com/chromedp/chromedp"
	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"

	"github.com/pricepoa/scraper-go/config"
	"github.com/pricepoa/scraper-go/scraper"
)

// RunChandaranaSpider runs the Chandarana spider
func RunChandaranaSpider(ctx context.Context, pricesColl *mongo.Collection, town string, branch string) {
	// Chandarana spider can accept town/branch for localization
	log.Println("Running Chandarana spider")
	if town != "" || branch != "" {
		branchConfig := config.ResolveBranch(town, branch)
		if branchConfig != nil {
			log.Printf("Chandarana spider using branch config: %s (%s)", branchConfig["name"], branchConfig["town"])
		} else {
			log.Printf("Chandarana spider received town=%s, branch=%s (using defaults)", town, branch)
		}
	}

	// Create chromedp context for JS rendering
	chromeCtx, cancel := chromedp.NewContext(ctx)
	defer cancel()

	var products []bson.M

	// Navigate to homepage and extract category links
	var homepageHTML string
	err := chromedp.Run(chromeCtx,
		chromedp.Navigate(`https://chandaranafoodplus.co.ke`),
		chromedp.OuterHTML(`html`, &homepageHTML),
	)
	if err != nil {
		log.Printf("Failed to fetch Chandarana homepage: %v", err)
		return
	}

	// Parse category links from homepage
	categoryLinks := extractChandaranaCategoryLinks(homepageHTML)
	log.Printf("Found %d category links on Chandarana homepage", len(categoryLinks))

	// Process each category link
	for _, categoryLink := range categoryLinks {
		// Extract category name from URL or link text for metadata
		category := extractCategoryFromURL(categoryLink)

		// Process category page (with pagination)
		categoryProducts := scrapeChandaranaCategory(chromeCtx, categoryLink, category, town, branch)
		products = append(products, categoryProducts...)

		// Be respectful - delay between categories
		time.Sleep(1 * time.Second)
	}

	if len(products) == 0 {
		log.Println("No products extracted from Chandarana")
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
		log.Printf("Inserted %d products from Chandarana", len(result.InsertedIDs))
	}
}

// extractChandaranaCategoryLinks extracts category links from the homepage HTML
func extractChandaranaCategoryLinks(html string) []string {
	var links []string

	// Use chromedp to extract links from HTML string
	ctx, cancel := chromedp.NewContext(context.Background())
	defer cancel()

	var nodes []*chromedp.Node
	err := chromedp.Run(ctx,
		chromedp.HTML(`<html><body>`+html+`</body></html>`, &nodes),
		chromedp.Nodes(`.main-menu a[href], .site-nav a[href], .menu-item a[href]`, &nodes, chromedp.ByQueryAll),
	)
	if err != nil {
		log.Printf("Error extracting category links with chromedp: %v", err)
		return extractChandaranaCategoryLinksFallback(html)
	}

	for _, node := range nodes {
		for _, attr := range node.Attributes {
			if attr.Key == "href" {
				link := attr.Val
				// Make absolute if relative
				if strings.HasPrefix(link, "/") {
					link = "https://chandaranafoodplus.co.ke" + link
				}
				// Filter for category links (avoid account, cart, etc.)
				if strings.Contains(link, "/collections/") || strings.Contains(link, "/shop/") {
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

// Fallback category link extraction
func extractChandaranaCategoryLinksFallback(html string) []string {
	var links []string
	// Simple extraction of href from menu areas
	start := 0
	for {
		startIdx := strings.Index(html[start:], `<a`)
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
			link = "https://chandaranafoodplus.co.ke" + link
		}
		// Filter for category links
		if strings.Contains(link, "/collections/") || strings.Contains(link, "/shop/") {
			links = append(links, link)
		}
	}
	return links
}

// extractCategoryFromURL tries to extract category name from URL
func extractCategoryFromURL(url string) string {
	// Try to extract category from URL path
	// Example: https://chandaranafoodplus.co.ke/collections/dairy -> dairy
	if idx := strings.LastIndex(url, "/collections/"); idx != -1 {
		category := url[idx+len("/collections/"):]
		// Remove trailing slash or query parameters
		if idx := strings.IndexAny(category, "/?"); idx != -1 {
			category = category[:idx]
		}
		// Replace hyphens with spaces and title case (simplified)
		category = strings.ReplaceAll(category, "-", " ")
		return strings.Title(category)
	}
	if idx := strings.LastIndex(url, "/shop/"); idx != -1 {
		category := url[idx+len("/shop/"):]
		if idx := strings.IndexAny(category, "/?"); idx != -1 {
			category = category[:idx]
		}
		category = strings.ReplaceAll(category, "-", " ")
		return strings.Title(category)
	}
	return "General"
}

// scrapeChandaranaCategory scrapes a category page (with pagination) and returns products
func scrapeChandaranaCategory(chromeCtx *chromedp.Context, categoryURL string, category string, town string, branch string) []bson.M {
	var products []bson.M

	// Create a task context for this category
	taskCtx, cancel := chromedp.NewContext(chromeCtx)
	defer cancel()

	// We'll handle pagination by looping until no next page
	currentURL := categoryURL
	pageNum := 1

	for currentURL != "" {
		log.Printf("Scraping Chandarana category page %d: %s", pageNum, currentURL)

		var pageHTML string
		err := chromedp.Run(taskCtx,
			chromedp.Navigate(currentURL),
			chromedp.OuterHTML(`html`, &pageHTML),
		)
		if err != nil {
			log.Printf("Failed to fetch Chandarana category page %s: %v", currentURL, err)
			break
		}

		// Extract product links from this page
		productLinks := extractChandaranaProductLinks(pageHTML)
		log.Printf("Found %d product links on page %d", len(productLinks), pageNum)

		// Process each product link
		for _, productLink := range productLinks {
			product := extractChandaranaProductDetails(chromeCtx, productLink, category)
			if product != nil {
				products = append(products, *product)
			}
			// Be respectful - small delay between requests
			time.Sleep(300 * time.Millisecond)
		}

		// Find next page link
		nextURL := extractChandaranaNextPageLink(pageHTML)
		if nextURL == "" || nextURL == currentURL {
			// No more pages or we're stuck
			break
		}
		currentURL = nextURL
		pageNum++
		// Be respectful - delay between pages
		time.Sleep(2 * time.Second)
	}

	return products
}

// extractChandaranaProductLinks extracts product links from a category page
func extractChandaranaProductLinks(html string) []string {
	var links []string

	// Use chromedp to extract links from HTML string
	ctx, cancel := chromedp.NewContext(context.Background())
	defer cancel()

	var nodes []*chromedp.Node
	err := chromedp.Run(ctx,
		chromedp.HTML(`<html><body>`+html+`</body></html>`, &nodes),
		chromedp.Nodes(`.product-item a[href], .product-card a[href], .grid-product__link[href]`, &nodes, chromedp.ByQueryAll),
	)
	if err != nil {
		log.Printf("Error extracting product links with chromedp: %v", err)
		return extractChandaranaProductLinksFallback(html)
	}

	for _, node := range nodes {
		for _, attr := range node.Attributes {
			if attr.Key == "href" {
				link := attr.Val
				// Make absolute if relative
				if strings.HasPrefix(link, "/") {
					link = "https://chandaranafoodplus.co.ke" + link
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
func extractChandaranaProductLinksFallback(html string) []string {
	var links []string
	// Simple extraction of href from product containers
	start := 0
	for {
		startIdx := strings.Index(html[start:], `<a`)
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
			link = "https://chandaranafoodplus.co.ke" + link
		}
		// Filter for product links
		if strings.Contains(link, "/products/") {
			links = append(links, link)
		}
	}
	return links
}

// extractChandaranaNextPageLink extracts the next page link from a category page
func extractChandaranaNextPageLink(html string) string {
	// Use chromedp to find next page link
	ctx, cancel := chromedp.NewContext(context.Background())
	defer cancel()

	var nextURL string
	err := chromedp.Run(ctx,
		chromedp.HTML(`<html><body>`+html+`</body></html>`, &nextURL),
		chromedp.Attribute(`a[rel="next"], .next, .pagination__next`, "href", &nextURL, chromedp.ByQueryAll),
	)
	if err != nil {
		// Fallback to simple extraction
		return extractChandaranaNextPageLinkFallback(html)
	}

	// Make absolute if relative
	if strings.HasPrefix(nextURL, "/") {
		nextURL = "https://chandaranafoodplus.co.ke" + nextURL
	}
	return nextURL
}

// Fallback next page link extraction
func extractChandaranaNextPageLinkFallback(html string) string {
	// Simple extraction of next page link
	start := 0
	for {
		startIdx := strings.Index(html[start:], `a[rel="next"]`)
		if startIdx == -1 {
			startIdx = strings.Index(html[start:], `.next`)
			if startIdx == -1 {
				startIdx = strings.Index(html[start:], `.pagination__next`)
			}
		}
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
		nextURL := html[start : start+endIdx]
		start += endIdx

		// Make absolute if relative
		if strings.HasPrefix(nextURL, "/") {
			nextURL = "https://chandaranafoodplus.co.ke" + nextURL
		}
		return nextURL
	}
	return ""
}

// extractChandaranaProductDetails navigates to a product URL and extracts product information
func extractChandaranaProductDetails(chromeCtx *chromedp.Context, productURL string, category string) *bson.M {
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
	product := extractChandaranaFromJSONLD(html, productURL, category)
	if product != nil {
		return product
	}

	// Fallback to CSS selectors
	return extractChandaranaFromCSS(html, productURL, category)
}

// extractChandaranaFromJSONLD tries to parse product data from JSON-LD scripts
func extractChandaranaFromJSONLD(html string, productURL string, category string) *bson.M {
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
		return extractChandaranaFromJSONLDFallback(html, productURL, category)
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
					"store_chain":    "Chandarana",
					"store_branch":   "Online Store",
					"price_kes":      price,
					"currency":       "KES",
					"source":         "chandarana_online",
					"is_promotional": isPromotional,
					"promotion_details": promotionDetails,
					"category":       category,
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
func extractChandaranaFromJSONLDFallback(html string, productURL string, category string) *bson.M {
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
					"store_chain":    "Chandarana",
					"store_branch":   "Online Store",
					"price_kes":      price,
					"currency":       "KES",
					"source":         "chandarana_online",
					"is_promotional": isPromotional,
					"promotion_details": promotionDetails,
					"category":       category,
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

// extractChandaranaFromCSS extracts product details using CSS selectors (fallback)
func extractChandaranaFromCSS(html string, productURL string, category string) *bson.M {
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
		`.product-single__title`,
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
		`.price-sale`,
		`.price`,
		`[class*="price"]`,
		`.cost`,
		`.product-price`,
		`.price__sale`,
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
		`.price-was`,
		`.original-price`,
		`.sale-tag`,
		`.price__compare`,
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
			chromedp.Text(`.price-was`, &wasPrice, chromedp.ByQuery),
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
		"store_chain":    "Chandarana",
		"store_branch":   "Online Store",
		"price_kes":      price,
		"currency":       "KES",
		"source":         "chandarana_online",
		"is_promotional": isPromotional,
		"promotion_details": promotionDetails,
		"category":       category,
		"response_url":   productURL,
		"verified_at":    time.Now(),
		"created_at":     time.Now(),
		"scraper":        "go",
	}
}