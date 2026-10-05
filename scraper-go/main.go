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

	"github.com/pricepoa/scraper-go/spiders"
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
	// Schedule quickmart_spider to run daily at 4 AM
	c.AddFunc("0 4 * * *", func() {
		log.Println("Running scheduled scrape for quickmart_spider")
		runSpiderOnce("quickmart_spider", town, branch) // pass town and branch for localization
	})
	// Schedule carrefour_spider to run daily at 5 AM
	c.AddFunc("0 5 * * *", func() {
		log.Println("Running scheduled scrape for carrefour_spider")
		runSpiderOnce("carrefour_spider", town, branch) // pass town and branch for localization
	})
	// Schedule chandarana_spider to run daily at 6 AM
	c.AddFunc("0 6 * * *", func() {
		log.Println("Running scheduled scrape for chandarana_spider")
		runSpiderOnce("chandarana_spider", town, branch) // pass town and branch for localization
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
		spiders.RunTheBarSpider(ctx, pricesColl, town, branch)
	case "naivas_spider":
		spiders.RunNaivasSpider(ctx, pricesColl, town, branch)
	case "quickmart_spider":
		spiders.RunQuickmartSpider(ctx, pricesColl, town, branch)
	case "carrefour_spider":
		spiders.RunCarrefourSpider(ctx, pricesColl, town, branch)
	case "chandarana_spider":
		spiders.RunChandaranaSpider(ctx, pricesColl, town, branch)
	// Add other spiders here
	default:
		log.Printf("Spider %s not implemented yet", spiderName)
	}
}