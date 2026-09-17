package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/chromedp/chromedp"
	"github.com/robfig/cron/v3"
	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
)

// Configuration from environment variables
var (
	mongoURI     = getEnv("MONGO_URI", "mongodb://pricepoa_dev:pricepoa_dev_password@mongo:27017/pricepoa?authSource=admin")
	mongoDBName  = getEnv("MONGODB_DB", "pricepoa")
	logLevel     = getEnv("SCRAPER_LOG_LEVEL", "info")
)

func getEnv(key, fallback string) string {
	if value, ok := os.LookupEnv(key); ok {
		return value
	}
	return fallback
}

func main() {
	// Define command-line flags
	mode := flag.String("mode", "scheduled", "Operation mode: scheduled, once, or test")
	spider := flag.String("spider", "", "Limit to a single spider (e.g. thebar_spider)")
	town := flag.String("town", "", "Specify town/city for localized spiders")
	branch := flag.String("branch", "", "Specify specific branch name/keyword for localized spiders")
	flag.Parse()

	log.Printf("Starting PricePoa Go scraper in %s mode", *mode)

	switch *mode {
	case "scheduled":
		runScheduledMode(*spider, *town, *branch)
	case "once":
		runOnceMode(*spider, *town, *branch)
	case "test":
		// Default to naivas_spider if none given for test mode
		if *spider == "" {
			*spider = "naivas_spider"
		}
		runOnceMode(*spider, *town, *branch)
	default:
		log.Fatalf("Unknown mode: %s", *mode)
	}
}

func runScheduledMode(spider string, town string, branch string) {
	log.Println("Starting in scheduled mode")
	// Setup cron scheduler
	c := cron.New()
	// Example: schedule thebar_spider to run daily at 2 AM
	// We'll hardcode for now, but ideally we'd read from a config or database
	c.AddFunc("0 2 * * *", func() {
		log.Println("Running scheduled scrape for thebar_spider")
		runSpiderOnce("thebar_spider", "", "") // town and branch not used for thebar
	})
	// Add more schedules for other spiders as needed
	// Schedule naivas_spider to run daily at 3 AM
	c.AddFunc("0 3 * * *", func() {
		log.Println("Running scheduled scrape for naivas_spider")
		runSpiderOnce("naivas_spider", "", "") // town and branch handled inside if needed
	})

	c.Start()
	defer c.Stop()

	// Wait for termination signal
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)
	<-sigChan
	log.Println("Shutting down scheduler...")
}

func runOnceMode(spider string, town string, branch string) {
	if spider != "" {
		log.Printf("Running single spider: %s", spider)
		runSpiderOnce(spider, town, branch)
	} else {
		log.Println("Running all spiders")
		// List of spiders to run
		spiders := []string{"thebar_spider", "naivas_spider", "carrefour_spider", "quickmart_spider", "chandarana_spider"}
		for _, s := range spiders {
			// For quickmart_spider, we might need to pass town/branch
			var t, b string
			if s == "quickmart_spider" {
				t = town
				b = branch
			}
			runSpiderOnce(s, t, b)
		}
	}
}

func runSpiderOnce(spiderName string, town string, branch string) {
	log.Printf("Running spider: %s", spiderName)
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Minute)
	defer cancel()

	// Initialize MongoDB client
	mongoClient, err := mongo.Connect(ctx, options.Client().ApplyURI(mongoURI))
	if err != nil {
		log.Fatalf("Failed to connect to MongoDB: %v", err)
	}
	defer mongoClient.Disconnect(ctx)

	// Test connection
	if err := mongoClient.Ping(ctx, nil); err != nil {
		log.Fatalf("Failed to ping MongoDB: %v", err)
	}

	// Get database and collection
	db := mongoClient.Database(mongoDBName)
	pricesColl := db.Collection("prices") // Assuming we store in the prices collection

	// Run the appropriate spider
	switch spiderName {
	case "thebar_spider":
		runTheBarSpider(ctx, pricesColl, town, branch)
	case "naivas_spider":
		runNaivasSpider(ctx, pricesColl, town, branch)
	// Add other spiders here
	default:
		log.Printf("Spider %s not implemented yet", spiderName)
	}
}

func runTheBarSpider(ctx context.Context, pricesColl *mongo.Collection, town string, branch string) {
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

func runNaivasSpider(ctx context.Context, pricesColl *mongo.Collection, town string, branch string) {
	// Naivas spider can accept town/branch for future localization, but currently
	// scrapes the national online store
	log.Println("Running Naivas spider")
	if town != "" || branch != "" {
		log.Printf("Naivas spider received town=%s, branch=%s (currently scraping national store)", town, branch)
	}

	// Create chromedp context for JS rendering
	chromeCtx, cancel := chromedp.NewContext(ctx)
	defer cancel()

	var products []bson.M

	// Navigate to homepage and extract category links
	var homepageHTML string
	err := chromedp.Run(chromeCtx,
		chromedp.Navigate(`https://naivas.online`),
		chromedp.OuterHTML(`html`, &homepageHTML),
	)
	if err != nil {
		log.Printf("Failed to fetch Naivas homepage: %v", err)
		return
	}

	// Parse category links from homepage
	categoryLinks := extractNaivasCategoryLinks(homepageHTML)
	log.Printf("Found %d category links on Naivas homepage", len(categoryLinks))

	// Limit for testing if needed (remove in production)
	// if len(categoryLinks) > 5 {
	// 	categoryLinks = categoryLinks[:5]
	// }

	// Process each category link
	for _, categoryLink := range categoryLinks {
		// Extract category name from URL or link text for metadata
		category := extractCategoryFromURL(categoryLink)

		// Process category page (with pagination)
		categoryProducts := scrapeNaivasCategory(chromeCtx, categoryLink, category, town, branch)
		products = append(products, categoryProducts...)

		// Be respectful - delay between categories
		time.Sleep(1 * time.Second)
	}

	if len(products) == 0 {
		log.Println("No products extracted from Naivas")
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
		log.Printf("Inserted %d products from Naivas", len(result.InsertedIDs))
	}
}

// extractNaivasCategoryLinks extracts category links from the homepage
func extractNaivasCategoryLinks(html string) []string {
	var links []string

	// Use chromedp to extract links from HTML string
	ctx, cancel := chromedp.NewContext(context.Background())
	defer cancel()

	var nodes []*chromedp.Node
	err := chromedp.Run(ctx,
		chromedp.HTML(`<html><body>`+html+`</body></html>`, &nodes),
		chromedp.Nodes(`#mega-menu-full a[href]`, &nodes, chromedp.ByQueryAll),
	)
	if err != nil {
		log.Printf("Error extracting category links with chromedp: %v", err)
		return extractNaivasCategoryLinksFallback(html)
	}

	for _, node := range nodes {
		for _, attr := range node.Attributes {
			if attr.Key == "href" {
				link := attr.Val
				// Make absolute if relative
				if strings.HasPrefix(link, "/") {
					link = "https://naivas.online" + link
				}
				// Filter for category links (avoid javascript:, mailto:, etc.)
				if strings.HasPrefix(link, "http") && strings.Contains(link, "/category/") {
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
func extractNaivasCategoryLinksFallback(html string) []string {
	var links []string
	// Simple extraction of href from #mega-menu-full a
	start := 0
	for {
		startIdx := strings.Index(html[start:], `<a`)
		if startIdx == -1 {
			break
		}
		start += startIdx
		// Check if this <a> is within #mega-menu-full
		// Simplified: just look for href after <a
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
			link = "https://naivas.online" + link
		}
		// Filter for category links
		if strings.Contains(link, "/category/") {
			links = append(links, link)
		}
	}
	return links
}

// extractCategoryFromURL tries to extract category name from URL
func extractCategoryFromURL(url string) string {
	// Try to extract category from URL path
	// Example: https://naivas.online/category/dairy-eggs -> dairy-eggs
	if idx := strings.LastIndex(url, "/category/"); idx != -1 {
		category := url[idx+len("/category/"):]
		// Remove trailing slash or query parameters
		if idx := strings.IndexAny(category, "/?"); idx != -1 {
			category = category[:idx]
		}
		// Replace hyphens with spaces and title case (simplified)
		category = strings.ReplaceAll(category, "-", " ")
		return strings.Title(category)
	}
	return "General"
}

// scrapeNaivasCategory scrapes a category page (with pagination) and returns products
func scrapeNaivasCategory(chromeCtx *chromedp.Context, categoryURL string, category string, town string, branch string) []bson.M {
	var products []bson.M

	// Create a task context for this category
	taskCtx, cancel := chromedp.NewContext(chromeCtx)
	defer cancel()

	// We'll handle pagination by looping until no next page
	currentURL := categoryURL
	pageNum := 1

	for currentURL != "" {
		log.Printf("Scraping Naivas category page %d: %s", pageNum, currentURL)

		var pageHTML string
		err := chromedp.Run(taskCtx,
			chromedp.Navigate(currentURL),
			chromedp.OuterHTML(`html`, &pageHTML),
		)
		if err != nil {
			log.Printf("Failed to fetch Naivas category page %s: %v", currentURL, err)
			break
		}

		// Extract product links from this page
		productLinks := extractNaivasProductLinks(pageHTML)
		log.Printf("Found %d product links on page %d", len(productLinks), pageNum)

		// Process each product link
		for _, productLink := range productLinks {
			product := extractNaivasProductDetails(chromeCtx, productLink, category)
			if product != nil {
				products = append(products, *product)
			}
			// Be respectful - small delay between requests
			time.Sleep(300 * time.Millisecond)
		}

		// Find next page link
		nextURL := extractNaivasNextPageLink(pageHTML)
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

// extractNaivasProductLinks extracts product links from a category page
func extractNaivasProductLinks(html string) []string {
	var links []string

	// Use chromedp to extract links from HTML string
	ctx, cancel := chromedp.NewContext(context.Background())
	defer cancel()

	var nodes []*chromedp.Node
	err := chromedp.Run(ctx,
		chromedp.HTML(`<html><body>`+html+`</body></html>`, &nodes),
		chromedp.Nodes(`.product-img a[href]`, &nodes, chromedp.ByQueryAll),
	)
	if err != nil {
		log.Printf("Error extracting product links with chromedp: %v", err)
		return extractNaivasProductLinksFallback(html)
	}

	for _, node := range nodes {
		for _, attr := range node.Attributes {
			if attr.Key == "href" {
				link := attr.Val
				// Make absolute if relative
				if strings.HasPrefix(link, "/") {
					link = "https://naivas.online" + link
				}
				// Filter for product links
				if strings.Contains(link, "/product/") || strings.Contains(link, "/products/") {
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
func extractNaivasProductLinksFallback(html string) []string {
	var links []string
	// Simple extraction of href from .product-img a
	start := 0
	for {
		startIdx := strings.Index(html[start:], `<a`)
		if startIdx == -1 {
			break
		}
		start += startIdx
		// Check if this <a> is within .product-img
		// Simplified: just look for href after <a
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
			link = "https://naivas.online" + link
		}
		// Filter for product links
		if strings.Contains(link, "/product/") || strings.Contains(link, "/products/") {
			links = append(links, link)
		}
	}
	return links
}

// extractNaivasNextPageLink extracts the next page link from a category page
func extractNaivasNextPageLink(html string) string {
	// Use chromedp to find next page link
	ctx, cancel := chromedp.NewContext(context.Background())
	defer cancel()

	var nextURL string
	err := chromedp.Run(ctx,
		chromedp.HTML(`<html><body>`+html+`</body></html>`, &nextURL),
		chromedp.Attribute(`a[rel="next"], .next-page, .pagination__next`, "href", &nextURL, chromedp.ByQueryAll),
	)
	if err != nil {
		// Fallback to simple extraction
		return extractNaivasNextPageLinkFallback(html)
	}

	// Make absolute if relative
	if strings.HasPrefix(nextURL, "/") {
		nextURL = "https://naivas.online" + nextURL
	}
	return nextURL
}

// Fallback next page link extraction
func extractNaivasNextPageLinkFallback(html string) string {
	// Simple extraction of next page link
	start := 0
	for {
		startIdx := strings.Index(html[start:], `a[rel="next"]`)
		if startIdx == -1 {
			startIdx = strings.Index(html[start:], `.next-page`)
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
			nextURL = "https://naivas.online" + nextURL
		}
		return nextURL
	}
	return ""
}

// extractNaivasProductDetails navigates to a product URL and extracts product information
func extractNaivasProductDetails(chromeCtx *chromedp.Context, productURL string, category string) *bson.M {
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
	product := extractNaivasFromJSONLD(html, productURL, category)
	if product != nil {
		return product
	}

	// Fallback to CSS selectors
	return extractNaivasFromCSS(html, productURL, category)
}

// extractNaivasFromJSONLD tries to parse product data from JSON-LD scripts
func extractNaivasFromJSONLD(html string, productURL string, category string) *bson.M {
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
		return extractNaivasFromJSONLDFallback(html, productURL, category)
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
				name := extractString(itemMap, "name")
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
					"store_chain":    "Naivas",
					"store_branch":   "Online Store",
					"price_kes":      price,
					"currency":       "KES",
					"source":         "naivas_online",
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
func extractNaivasFromJSONLDFallback(html string, productURL string, category string) *bson.M {
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
				name := extractString(itemMap, "name")
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
					"store_chain":    "Naivas",
					"store_branch":   "Online Store",
					"price_kes":      price,
					"currency":       "KES",
					"source":         "naivas_online",
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

// extractNaivasFromCSS extracts product details using CSS selectors (fallback)
func extractNaivasFromCSS(html string, productURL string, category string) *bson.M {
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
		`.price-sale`,
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
		`.price-was`,
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
	price := cleanPrice(priceText)

	return &bson.M{
		"product_name":   strings.TrimSpace(productName),
		"store_chain":    "Naivas",
		"store_branch":   "Online Store",
		"price_kes":      price,
		"currency":       "KES",
		"source":         "naivas_online",
		"is_promotional": isPromotional,
		"promotion_details": promotionDetails,
		"category":       category,
		"response_url":   productURL,
		"verified_at":    time.Now(),
		"created_at":     time.Now(),
		"scraper":        "go",
	}
}

// extractString helper for JSON-LD parsing
func extractString(data map[string]interface{}, key string) string {
	if val, ok := data[key]; ok {
		switch v := val.(type) {
		case string:
			return v
		case float64:
			return fmt.Sprintf("%.2f", v)
		}
	}
	return ""
}

// cleanPrice removes currency symbols and extra text from price string
func cleanPrice(priceText string) string {
	// Remove common currency symbols and text
	price := strings.TrimSpace(priceText)
	price = strings.ReplaceAll(price, "KES", "")
	price = strings.ReplaceAll(price, "KSh", "")
	price = strings.ReplaceAll(price, "£", "")
	price = strings.ReplaceAll(price, "$", "")
	price = strings.ReplaceAll(price, ",", "")
	price = strings.TrimSpace(price)

	// Extract first number-like pattern
	// Simple approach: find first sequence of digits and optional decimal
	// In production, you might want to use regex
	return price
}