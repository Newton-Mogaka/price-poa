package scraper

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"strings"
	"sync"
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

// ScraperContext holds shared resources for scraping operations
type ScraperContext struct {
	MongoClient *mongo.Client
	DB          *mongo.Database
	PricesColl  *mongo.Collection
	WG          *sync.WaitGroup
	Mutex       *sync.Mutex
}

// NewScraperContext initializes MongoDB connection and returns a scraper context
func NewScraperContext() (*ScraperContext, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	// Initialize MongoDB client
	mongoClient, err := mongo.Connect(ctx, options.Client().ApplyURI(mongoURI))
	if err != nil {
		return nil, fmt.Errorf("failed to connect to MongoDB: %w", err)
	}

	// Test connection
	if err := mongoClient.Ping(ctx, nil); err != nil {
		return nil, fmt.Errorf("failed to ping MongoDB: %w", err)
	}

	// Get database and collection
	db := mongoClient.Database(mongoDBName)
	pricesColl := db.Collection("prices")

	return &ScraperContext{
		MongoClient: mongoClient,
		DB:          db,
		PricesColl:  pricesColl,
		WG:          &sync.WaitGroup{},
		Mutex:       &sync.Mutex{},
	}, nil
}

// Close closes the MongoDB connection
func (ctx *ScraperContext) Close() {
	if ctx.MongoClient != nil {
		ctx.MongoClient.Disconnect(context.Background())
	}
}

// InsertProducts inserts multiple product documents into the prices collection
func (ctx *ScraperContext) InsertProducts(ctxContext context.Context, products []bson.M) error {
	if len(products) == 0 {
		return nil
	}

	var docs []interface{}
	for _, p := range products {
		docs = append(docs, p)
	}

	insertManyOpts := options.InsertMany().SetOrdered(false)
	_, err := ctx.PricesColl.InsertMany(ctxContext, docs, insertManyOpts)
	if err != nil {
		return fmt.Errorf("failed to insert products: %w", err)
	}

	return nil
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