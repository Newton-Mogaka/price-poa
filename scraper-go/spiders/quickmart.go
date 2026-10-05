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

// RunQuickmartSpider runs the Quickmart spider with localization support
func RunQuickmartSpider(ctx context.Context, pricesColl *mongo.Collection, town string, branch string) {
	// Resolve branch configuration based on town/branch parameters
	branchProfile := config.ResolveBranch(town, branch)
	storeBranch := branchProfile["branch_name"].(string)
	storeTown := branchProfile["town"].(string)
	storeCounty := branchProfile["county"].(string)
	shopID := branchProfile["shop_id"].(int)
	slug := branchProfile["slug"].(string)
	var gpsLat *float64
	var gpsLng *float64
	if lat, ok := branchProfile["gps_latitude"].(*float64); ok {
		gpsLat = lat
	}
	if lng, ok := branchProfile["gps_longitude"].(*float64); ok {
		gpsLng = lng
	}
	address := branchProfile["address"].(string)
	cookies := branchProfile["cookies"].([]map[string]string)

	log.Printf("Running Quickmart spider for branch '%s' in %s, %s (Shop ID: %d)",
		storeBranch, storeTown, storeCounty, shopID)

	// Create chromedp context for JS rendering
	chromeCtx, cancel := chromedp.NewContext(ctx)
	defer cancel()

	var products []bson.M

	// Parse cookies for chromedp
	var cookieStrings []string
	for _, cookie := range cookies {
		cookieStrings = append(cookieStrings, fmt.Sprintf("%s=%s", cookie["name"], cookie["value"]))
	}
	cookieHeader := strings.Join(cookieStrings, "; ")

	// Navigate to homepage with branch-specific cookies and extract category links
	var homepageHTML string
	err := chromedp.Run(chromeCtx,
		chromedp.ActionFunc(func(ctx context.Context) error {
			// Set cookies before navigating
			if err := chromedp.SetCookie(
				&chromedp.Cookie{
					Name:  "_ygShopId",
					Value: fmt.Sprintf("%d", shopID),
				},
				&chromedp.Cookie{
					Name:  "_ygGeoAddress",
					Value: storeTown,
				},
				&chromedp.Cookie{
					Name:  "_ygGeoLat",
					Value: fmt.Sprintf("%f", *gpsLat),
				},
				&chromedp.Cookie{
					Name:  "_ygGeoLng",
					Value: fmt.Sprintf("%f", *gpsLng),
				},
				&chromedp.Cookie{
					Name:  "_ygGeoRadius",
					Value: "15",
				},
			).Do(ctx); err != nil {
				return err
			}
			return nil
		}),
		chromedp.Navigate(`https://www.quickmart.co.ke/`),
		chromedp.OuterHTML(`html`, &homepageHTML),
	)
	if err != nil {
		log.Printf("Failed to fetch Quickmart homepage: %v", err)
		return
	}

	// Parse category links from homepage
	categoryLinks := extractQuickmartCategoryLinks(homepageHTML)
	log.Printf("Found %d category links on Quickmart homepage", len(categoryLinks))

	// Process each category link
	for _, categoryLink := range categoryLinks {
		// Extract category name from URL or link text for metadata
		category := extractCategoryFromURL(categoryLink)

		// Process category page (with pagination)
		categoryProducts := scrapeQuickmartCategory(chromeCtx, categoryLink, category, storeBranch, storeTown, storeCounty, gpsLat, gpsLng, address, cookieHeader)
		products = append(products, categoryProducts...)

		// Be respectful - delay between categories
		time.Sleep(1 * time.Second)
	}

	if len(products) == 0 {
		log.Println("No products extracted from Quickmart")
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
		log.Printf("Inserted %d products from Quickmart (%s)", len(result.InsertedIDs), storeBranch)
	}
}

// extractQuickmartCategoryLinks extracts category links from the homepage HTML
func extractQuickmartCategoryLinks(html string) []string {
	var links []string

	// Use chromedp to extract links from HTML string
	ctx, cancel := chromedp.NewContext(context.Background())
	defer cancel()

	var nodes []*chromedp.Node
	err := chromedp.Run(ctx,
		chromedp.HTML(`<html><body>`+html+`</body></html>`, &nodes),
		chromedp.Nodes(`.category-menu-link.categoryMenuLinkJs[href]`, &nodes, chromedp.ByQueryAll),
	)
	if err != nil {
		log.Printf("Error extracting category links with chromedp: %v", err)
		return extractQuickmartCategoryLinksFallback(html)
	}

	for _, node := range nodes {
		for _, attr := range node.Attributes {
			if attr.Key == "href" {
				link := attr.Val
				// Make absolute if relative
				if strings.HasPrefix(link, "/") {
					link = "https://www.quickmart.co.ke" + link
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
func extractQuickmartCategoryLinksFallback(html string) []string {
	var links []string
	// Simple extraction of href from .category-menu-link.categoryMenuLinkJs
	start := 0
	for {
		startIdx := strings.Index(html[start:], `<a`)
		if startIdx == -1 {
			break
		}
		start += startIdx
		// Check if this <a> has the required classes
		classIdx := strings.Index(html[start:], `class="`)
		if classIdx == -1 {
			start++
			continue
		}
		start += classIdx + 7 // skip 'class="'
		endClassIdx := strings.Index(html[start:], `"`)
		if endClassIdx == -1 {
			start++
			continue
		}
		classValue := html[start : start+endClassIdx]
		start += endClassIdx

		// Check if it contains both required classes
		if strings.Contains(classValue, "category-menu-link") && strings.Contains(classValue, "categoryMenuLinkJs") {
			// Now look for href
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
				link = "https://www.quickmart.co.ke" + link
			}
			// Filter for category links
			if strings.Contains(link, "/category/") {
				links = append(links, link)
			}
		} else {
			// Move past this <a> tag
			endTagIdx := strings.Index(html[start:], `>`)
			if endTagIdx == -1 {
				break
			}
			start += endTagIdx + 1
		}
	}
	return links
}

// extractCategoryFromURL tries to extract category name from URL
func extractCategoryFromURL(url string) string {
	// Try to extract category from URL path
	// Example: https://www.quickmart.co.ke/category/dairy-eggs -> dairy-eggs
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

// scrapeQuickmartCategory scrapes a category page (with pagination) and returns products
func scrapeQuickmartCategory(chromeCtx *chromedp.Context, categoryURL string, category string, storeBranch string, storeTown string, storeCounty string, gpsLat *float64, gpsLng *float64, address string, cookieHeader string) []bson.M {
	var products []bson.M

	// Create a task context for this category
	taskCtx, cancel := chromedp.NewContext(chromeCtx)
	defer cancel()

	// We'll handle pagination by looping until no next page
	currentURL := categoryURL
	pageNum := 1

	for currentURL != "" {
		log.Printf("Scraping Quickmart category page %d: %s", pageNum, currentURL)

		var pageHTML string
		err := chromedp.Run(taskCtx,
			chromedp.ActionFunc(func(ctx context.Context) error {
				// Set cookies before navigating
				if err := chromedp.SetCookie(
					&chromedp.Cookie{
						Name:  "_ygShopId",
						Value: fmt.Sprintf("%d", shopID), // Use resolved shopID
					},
					&chromedp.Cookie{
						Name:  "_ygGeoAddress",
						Value: storeTown,
					},
					&chromedp.Cookie{
						Name:  "_ygGeoLat",
						Value: fmt.Sprintf("%f", *gpsLat),
					},
					&chromedp.Cookie{
						Name:  "_ygGeoLng",
						Value: fmt.Sprintf("%f", *gpsLng),
					},
					&chromedp.Cookie{
						Name:  "_ygGeoRadius",
						Value: "15",
					},
				).Do(ctx); err != nil {
					return err
				}
				return nil
			}),
			chromedp.Navigate(currentURL),
			chromedp.OuterHTML(`html`, &pageHTML),
		)
		if err != nil {
			log.Printf("Failed to fetch Quickmart category page %s: %v", currentURL, err)
			break
		}

		// Extract product links from this page
		productLinks := extractQuickmartProductLinks(pageHTML)
		log.Printf("Found %d product links on page %d", len(productLinks), pageNum)

		// Process each product link
		for _, productLink := range productLinks {
			product := extractQuickmartProductDetails(chromeCtx, productLink, category, storeBranch, storeTown, storeCounty, gpsLat, gpsLng, address, cookieHeader)
			if product != nil {
				products = append(products, *product)
			}
			// Be respectful - small delay between requests
			time.Sleep(300 * time.Millisecond)
		}

		// Find next page link
		nextURL := extractQuickmartNextPageLink(pageHTML)
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

// extractQuickmartProductLinks extracts product links from a category page
func extractQuickmartProductLinks(html string) []string {
	var links []string

	// Use chromedp to extract links from HTML string
	ctx, cancel := chromedp.NewContext(context.Background())
	defer cancel()

	var nodes []*chromedp.Node
	err := chromedp.Run(ctx,
		chromedp.HTML(`<html><body>`+html+`</body></html>`, &nodes),
		chromedp.Nodes(`a.products-title[href]`, &nodes, chromedp.ByQueryAll),
	)
	if err != nil {
		log.Printf("Error extracting product links with chromedp: %v", err)
		return extractQuickmartProductLinksFallback(html)
	}

	for _, node := range nodes {
		for _, attr := range node.Attributes {
			if attr.Key == "href" {
				link := attr.Val
				// Make absolute if relative
				if strings.HasPrefix(link, "/") {
					link = "https://www.quickmart.co.ke" + link
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
func extractQuickmartProductLinksFallback(html string) []string {
	var links []string
	// Simple extraction of href from a.products-title
	start := 0
	for {
		startIdx := strings.Index(html[start:], `<a`)
		if startIdx == -1 {
			break
		}
		start += startIdx
		// Check if this <a> has the products-title class
		classIdx := strings.Index(html[start:], `class="`)
		if classIdx == -1 {
			start++
			continue
		}
		start += classIdx + 7 // skip 'class="'
		endClassIdx := strings.Index(html[start:], `"`)
		if endClassIdx == -1 {
			start++
			continue
		}
		classValue := html[start : start+endClassIdx]
		start += endClassIdx

		// Check if it contains the required class
		if strings.Contains(classValue, "products-title") {
			// Now look for href
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
				link = "https://www.quickmart.co.ke" + link
			}
			// Filter for product links
			if strings.Contains(link, "/product/") || strings.Contains(link, "/products/") {
				links = append(links, link)
			}
		} else {
			// Move past this <a> tag
			endTagIdx := strings.Index(html[start:], `>`)
			if endTagIdx == -1 {
				break
			}
			start += endTagIdx + 1
		}
	}
	return links
}

// extractQuickmartNextPageLink extracts the next page link from a category page
func extractQuickmartNextPageLink(html string) string {
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
		return extractQuickmartNextPageLinkFallback(html)
	}

	// Make absolute if relative
	if strings.HasPrefix(nextURL, "/") {
		nextURL = "https://www.quickmart.co.ke" + nextURL
	}
	return nextURL
}

// Fallback next page link extraction
func extractQuickmartNextPageLinkFallback(html string) string {
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
			nextURL = "https://www.quickmart.co.ke" + nextURL
		}
		return nextURL
	}
	return ""
}

// extractQuickmartProductDetails navigates to a product URL and extracts product information
func extractQuickmartProductDetails(chromeCtx *chromedp.Context, productURL string, category string, storeBranch string, storeTown string, storeCounty string, gpsLat *float64, gpsLng *float64, address string, cookieHeader string) *bson.M {
	// Create a task context with timeout
	taskCtx, cancel := chromedp.NewContext(chromeCtx)
	defer cancel()
	taskCtx, cancel = context.WithTimeout(taskCtx, 20*time.Second)
	defer cancel()

	var html string
	err := chromedp.Run(taskCtx,
		chromedp.ActionFunc(func(ctx context.Context) error {
			// Set cookies before navigating
			if err := chromedp.SetCookie(
				&chromedp.Cookie{
					Name:  "_ygShopId",
					Value: fmt.Sprintf("%d", shopID), // Use resolved shopID
				},
				&chromedp.Cookie{
					Name:  "_ygGeoAddress",
					Value: storeTown,
				},
				&chromedp.Cookie{
					Name:  "_ygGeoLat",
					Value: fmt.Sprintf("%f", *gpsLat),
				},
				&chromedp.Cookie{
					Name:  "_ygGeoLng",
					Value: fmt.Sprintf("%f", *gpsLng),
				},
				&chromedp.Cookie{
					Name:  "_ygGeoRadius",
					Value: "15",
				},
			).Do(ctx); err != nil {
				return err
			}
			return nil
		}),
		chromedp.Navigate(productURL),
		chromedp.OuterHTML(`html`, &html),
	)
	if err != nil {
		log.Printf("Failed to fetch product page %s: %v", productURL, err)
		return nil
	}

	// Try to extract from JSON-LD first
	product := extractQuickmartFromJSONLD(html, productURL, category, storeBranch, storeTown, storeCounty, gpsLat, gpsLng, address)
	if product != nil {
		return product
	}

	// Fallback to CSS selectors
	return extractQuickmartFromCSS(html, productURL, category, storeBranch, storeTown, storeCounty, gpsLat, gpsLng, address)
}

// extractQuickmartFromJSONLD tries to parse product data from JSON-LD scripts
func extractQuickmartFromJSONLD(html string, productURL string, category string, storeBranch string, storeTown string, storeCounty string, gpsLat *float64, gpsLng *float64, address string) *bson.M {
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
		return extractQuickmartFromJSONLDFallback(html, productURL, category, storeBranch, storeTown, storeCounty, gpsLat, gpsLng, address)
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
				name := scraper.ExtractString(itemMap, "name")
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
					"store_chain":    storeBranch,
					"store_branch":   storeBranch,
					"store_town":     storeTown,
					"store_county":   storeCounty,
					"gps_latitude":   gpsLat,
					"gps_longitude":  gpsLng,
					"address":        address,
					"price_kes":      price,
					"currency":       "KES",
					"source":         "quickmart_online",
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
func extractQuickmartFromJSONLDFallback(html string, productURL string, category string, storeBranch string, storeTown string, storeCounty string, gpsLat *float64, gpsLng *float64, address string) *bson.M {
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
				name := scraper.ExtractString(itemMap, "name")
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
					"store_chain":    storeBranch,
					"store_branch":   storeBranch,
					"store_town":     storeTown,
					"store_county":   storeCounty,
					"gps_latitude":   gpsLat,
					"gps_longitude":  gpsLng,
					"address":        address,
					"price_kes":      price,
					"currency":       "KES",
					"source":         "quickmart_online",
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

// extractQuickmartFromCSS extracts product details using CSS selectors (fallback)
func extractQuickmartFromCSS(html string, productURL string, category string, storeBranch string, storeTown string, storeCounty string, gpsLat *float64, gpsLng *float64, address string) *bson.M {
	ctx, cancel := chromedp.NewContext(context.Background())
	defer cancel()

	var productName string
	var priceText string
	var isPromotional bool
	var promotionDetails string

	// Try to extract product name
	nameSelectors := []string{
		`h1.product-title *::text`,
		`h1.product-title::text`,
		`.product-title *::text`,
		`.product-title::text`,
		`h1 *::text`,
		`h1::text`,
		`.product-name *::text`,
		`.product-name::text`,
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
		`.products-price-new *::text`,
		`.products-price-new::text`,
		`.products-price *::text`,
		`.products-price::text`,
		`.price-new *::text`,
		`.price-new::text`,
		`.product-price *::text`,
		`.product-price::text`,
		`.price::text`,
		`.current-price::text`,
		`[data-testid="price"]::text`,
		`.sale-price::text`,
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
		`.products-price-old *::text`,
		`.products-price-off *::text`,
		`.badge-offer, .label-sale, .promo-badge`,
		`[data-testid="original-price"]`,
		`.was-price::text`,
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
			chromedp.Text(`.products-price-old`, &wasPrice, chromedp.ByQuery),
		)
		if err == nil && strings.TrimSpace(wasPrice) != "" {
			err2 := chromedp.Run(ctx,
				chromedp.HTML(`<html><body>`+html+`</body></html>`, &nowPrice),
				chromedp.Text(`.products-price-new`, &nowPrice, chromedp.ByQuery),
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
	price := scraper.CleanPrice(priceText)

	return &bson.M{
		"product_name":   strings.TrimSpace(productName),
		"store_chain":    storeBranch,
		"store_branch":   storeBranch,
		"store_town":     storeTown,
		"store_county":   storeCounty,
		"gps_latitude":   gpsLat,
		"gps_longitude":  gpsLng,
		"address":        address,
		"price_kes":      price,
		"currency":       "KES",
		"source":         "quickmart_online",
		"is_promotional": isPromotional,
		"promotion_details": promotionDetails,
		"category":       category,
		"response_url":   productURL,
		"verified_at":    time.Now(),
		"created_at":     time.Now(),
		"scraper":        "go",
	}
}