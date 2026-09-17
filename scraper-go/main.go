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

// extractProductLinks parses the collections page HTML and returns product URLs
func extractProductLinks(html string) []string {
	var links []string

	// Use chromedp to extract links from HTML string
	// We'll create a temporary context just for this extraction
	ctx, cancel := chromedp.NewContext(context.Background())
	defer cancel()

	var linkStrings []string
	err := chromedp.Run(ctx,
		chromedp.HTML(`<html><body>`+html+`</body></html>`, &linkStrings),
		chromedp.Nodes(`a[href*="/products/"]`, &linkStrings, chromedp.ByQueryAll),
	)
	if err != nil {
		log.Printf("Error extracting product links: %v", err)
		// Fallback: simple string parsing
		return extractProductLinksFallback(html)
	}

	// Actually, let's do it properly with chromedp
	var nodes []*chromedp.Node
	err = chromedp.Run(ctx,
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
				if strings.HasPrefix(link, "/") {
					link = "https://ke.thebar.com" + link
				}
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

// Fallback link extraction using simple string parsing
func extractProductLinksFallback(html string) []string {
	var links []string
	// Simple regex-like extraction for href containing /products/
	start := 0
	for {
		startIdx := strings.Index(html[start:], `href="`)
		if startIdx == -1 {
			break
		}
		start += startIdx + 6 // skip 'href="'
		endIdx := strings.Index(html[start:], `"`)
		if endIdx == -1 {
			break
		}
		link := html[start : start+endIdx]
		if strings.Contains(link, "/products/") {
			if strings.HasPrefix(link, "/") {
				link = "https://ke.thebar.com" + link
			}
			links = append(links, link)
		}
		start += endIdx
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

				// Build product document
				return &bson.M{
					"product_name":   strings.TrimSpace(name),
					"store_chain":    "The Bar",
					"store_branch":   "Online Store",
					"price_kes":      price,
					"currency":       "KES",
					"source":         "thebar_online",
					"category":       "Party",
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

				return &bson.M{
					"product_name":   strings.TrimSpace(name),
					"store_chain":    "The Bar",
					"store_branch":   "Online Store",
					"price_kes":      price,
					"currency":       "KES",
					"source":         "thebar_online",
					"category":       "Party",
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
	var category string

	// Try to extract product name
	nameSelectors := []string{
		`h1`,
		`.product-title`,
		`.product-name`,
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
		`.price-current`,
		`.sales-price`,
		`[data-testid="price"]`,
		`.price`,
		`[class*="price"]`,
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

	// Category is known to be Party from the collection URL
	category = "Party"

	if strings.TrimSpace(productName) == "" || strings.TrimSpace(priceText) == "" {
		log.Printf("Could not extract product name or price from %s", productURL)
		return nil
	}

	// Clean price text (remove currency symbols, etc.)
	price := cleanPrice(priceText)

	return &bson.M{
		"product_name":   strings.TrimSpace(productName),
		"store_chain":    "The Bar",
		"store_branch":   "Online Store",
		"price_kes":      price,
		"currency":       "KES",
		"source":         "thebar_online",
		"is_promotional": false, // TODO: detect promotions
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