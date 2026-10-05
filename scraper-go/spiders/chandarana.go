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
	// Chandarana spider can accept town/branch for future localization, but currently
	// scrapes the national online store
	log.Println("Running Chandarana spider")
	if town != "" || branch != "" {
		log.Printf("Chandarana spider received town=%s, branch=%s (currently scraping national store)", town, branch)
	}

	// Create chromedp context for JS rendering
	chromeCtx, cancel := chromedp.NewContext(ctx)
	defer cancel()

	var products []bson.M

	// Navigate to homepage and extract category links
	var homepageHTML string
	err := chromedp.Run(chromeCtx,
		chromedp.Navigate(`https://www.chandarana.co.ke`),
		chromedp.OuterHTML(`html`, &homepageHTML),
	)
	if err != nil {
		log.Printf("Failed to fetch Chandarana homepage: %v", err)
		return
	}

	// Parse category links from homepage (placeholder selector)
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
	// TODO: Implement proper selector for Chandarana category links
	// For now, return empty slice to avoid breaking
	log.Println("extractChandaranaCategoryLinks: not implemented")
	return []string{}
}

// extractCategoryFromURL tries to extract category name from URL
func extractCategoryFromURL(url string) string {
	// Try to extract category from URL path
	// Example: https://www.chandarana.co.ke/category/dairy-eggs -> dairy-eggs
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

// scrapeChandaranaCategory scrapes a category page (with pagination) and returns products
func scrapeChandaranaCategory(chromeCtx *chromedp.Context, categoryURL string, category string, town string, branch string) []bson.M {
	// TODO: Implement proper scraping for Chandarana category pages
	log.Println("scrapeChandaranaCategory: not implemented")
	return []bson.M{}
}

// Helper functions for product extraction (stubs)
func extractChandaranaProductDetails(chromeCtx *chromedp.Context, productURL string, category string) *bson.M {
	// TODO: Implement product detail extraction for Chandarana
	log.Printf("extractChandaranaProductDetails: not implemented for %s", productURL)
	return nil
}