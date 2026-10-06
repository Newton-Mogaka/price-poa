package spiders

import (
	"context"
	"strings"

	"go.mongodb.org/mongo-driver/mongo"

	"github.com/pricepoa/scraper-go/scraper"
)

// RunTheBarSpider scrapes the "party" collection on The Bar (town/branch not used).
func RunTheBarSpider(ctx context.Context, pricesColl *mongo.Collection, town string, branch string) {
	scraper.RunStore(ctx, pricesColl, scraper.StoreConfig{
		Chain:  "The Bar",
		Branch: "Online Store",
		Source: "thebar_online",

		// No category discovery: the collection page is the only page, saved under "Party".
		StartURL:      "https://ke.thebar.com/collections/party",
		FixedCategory: "Party",
		ProductSel:    `a[href*="/products/"]`,
		ProductOK:     func(l string) bool { return strings.Contains(l, "/products/") },

		PriceSels: []string{`.sales-price`},
		PromoSels: []string{`.was-price`},
		WasSel:    ".was-price",
	})
}