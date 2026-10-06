package spiders

import (
	"context"
	"strings"

	"go.mongodb.org/mongo-driver/mongo"

	"github.com/pricepoa/scraper-go/scraper"
)

// RunNaivasSpider scrapes the national Naivas online store (town/branch not used yet).
func RunNaivasSpider(ctx context.Context, pricesColl *mongo.Collection, town string, branch string) {
	scraper.RunStore(ctx, pricesColl, scraper.StoreConfig{
		Chain:  "Naivas",
		Branch: "Online Store",
		Source: "naivas_online",

		StartURL:    "https://naivas.online",
		CategorySel: `#mega-menu-full a[href]`,
		CategoryOK:  func(l string) bool { return strings.Contains(l, "/category/") },
		ProductSel:  `.product-img a[href]`,
		ProductOK: func(l string) bool {
			return strings.Contains(l, "/product/") || strings.Contains(l, "/products/")
		},
		NextSel: `a[rel="next"], a.next-page, .next-page a, a.pagination__next, .pagination__next a`,
	})
}