package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/chromedp/chromedp"
	"github.com/robfig/cron/v3"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
)

// Configuration from environment variables
var (
	mongoURI     = getEnv("MONGO_URI", "mongodb://pricepoa_dev:pricepoa_dev_password@mongo:27017/pricepoa?authSource=admin")
	mongoDBName  = getEnv("MONGODB_DB", "pricepoa")
	logLevel     = getEnv("SCRAPER_LOG_LEVEL", "info")
	// Add other env vars as needed
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

	// Set up a timeout for chromedp tasks
	taskCtx, cancel := context.WithTimeout(chromeCtx, 30*time.Second)
	defer cancel()

	// Navigate to the start URL
	var html string
	err := chromedp.Run(taskCtx,
		chromedp.Navigate(`https://ke.thebar.com/collections/party`),
		chromedp.OuterHTML(`html`, &html),
	)
	if err != nil {
		log.Printf("Failed to fetch The Bar page: %v", err)
		return
	}

	// TODO: Parse HTML to extract product links and then product details
	// For now, we'll just log that we got the page
	log.Printf("Fetched The Bar page, length: %d", len(html))

	// TODO: Implement parsing logic similar to the Python spider
	// For demonstration, we'll insert a dummy document
	dummyPrice := map[string]interface{}{
		"product_name":   "Dummy Product from Go",
		"store_chain":    "The Bar",
		"store_branch":   "Online Store",
		"price_kes":      "100",
		"currency":       "KES",
		"source":         "thebar_online",
		"category":       "Party",
		"verified_at":    time.Now(),
		"created_at":     time.Now(),
		"response_url":   "https://ke.thebar.com/collections/party",
		"scraper":        "go",
	}

	insertResult, err := pricesColl.InsertOne(ctx, dummyPrice)
	if err != nil {
		log.Printf("Failed to insert dummy price: %v", err)
		return
	}
	log.Printf("Inserted dummy price with ID: %v", insertResult.InsertedID)
}