package spiders

import (
	"context"
	"log"
	"strings"

	"go.mongodb.org/mongo-driver/mongo"

	"github.com/pricepoa/scraper-go/config"
	"github.com/pricepoa/scraper-go/scraper"
)

// RunChandaranaSpider scrapes Chandarana Foodplus.
func RunChandaranaSpider(ctx context.Context, pricesColl *mongo.Collection, town string, branch string) {
	if town != "" || branch != "" {
		if branchConfig := config.ResolveBranch(town, branch); branchConfig != nil {
			log.Printf("Chandarana spider using branch config: %v (%v)", branchConfig["name"], branchConfig["town"])
		} else {
			log.Printf("Chandarana spider received town=%s, branch=%s (using defaults)", town, branch)
		}
	}

	scraper.RunStore(ctx, pricesColl, scraper.StoreConfig{
		Chain:  "Chandarana",
		Branch: "Online Store",
		Source: "chandarana_online",

		StartURL:    "https://chandaranafoodplus.co.ke",
		CategorySel: `.main-menu a[href], .site-nav a[href], .menu-item a[href]`,
		CategoryOK: func(l string) bool {
			return strings.Contains(l, "/collections/") || strings.Contains(l, "/shop/")
		},
		ProductSel: `.product-item a[href], .product-card a[href], .grid-product__link[href]`,
		ProductOK:  func(l string) bool { return strings.Contains(l, "/products/") },
		NextSel:    `a[rel="next"], a.next, .next a, a.pagination__next, .pagination__next a`,

		NameSels:  []string{`.product-single__title`},
		PriceSels: []string{`.product-price`, `.price__sale`},
		PromoSels: []string{`.sale-tag`, `.price__compare`},
	})
}