package spiders

import (
	"context"
	"strings"

	"go.mongodb.org/mongo-driver/mongo"

	"github.com/pricepoa/scraper-go/scraper"
)

// RunCarrefourSpider scrapes the national Carrefour online store (town/branch not used yet).
func RunCarrefourSpider(ctx context.Context, pricesColl *mongo.Collection, town string, branch string) {
	scraper.RunStore(ctx, pricesColl, scraper.StoreConfig{
		Chain:  "Carrefour",
		Branch: "Online Store",
		Source: "carrefour_online",

		StartURL:    "https://www.carrefour.co.ke",
		CategorySel: `nav a[href*="/category/"], .menu a[href*="/category/"], .nav-menu a[href*="/category/"]`,
		CategoryOK:  func(l string) bool { return strings.Contains(l, "/category/") },
		ProductSel:  `a[href*="/product/"], a[href*="/products/"], .product-item a[href]`,
		ProductOK: func(l string) bool {
			return strings.Contains(l, "/product/") || strings.Contains(l, "/products/")
		},
		NextSel: `a[rel="next"], a.next-page, .next-page a, a.pagination__next, .pagination__next a`,
	})
}