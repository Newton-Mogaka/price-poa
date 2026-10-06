package spiders

import (
	"context"
	"net/url"
	"strings"

	"go.mongodb.org/mongo-driver/mongo"

	"github.com/pricepoa/scraper-go/scraper"
)

// Naivas product URLs are a single path segment, e.g. /naivas-fino-uht-milk-500ml
func isNaivasProduct(link string) bool {
	u, err := url.Parse(link)
	if err != nil || !strings.HasSuffix(u.Host, "naivas.online") || u.RawQuery != "" {
		return false
	}
	seg := strings.Trim(u.Path, "/")
	return seg != "" && !strings.Contains(seg, "/")
}

func RunNaivasSpider(ctx context.Context, pricesColl *mongo.Collection, town string, branch string) {
	scraper.RunStore(ctx, pricesColl, scraper.StoreConfig{
		Chain:  "Naivas",
		Branch: "Online Store",
		Source: "naivas_online",

		StartURL:    "https://www.naivas.online",
		CategorySel: `a[title="#"]`, // the mega-menu links
		CategoryOK:  func(l string) bool { return !strings.Contains(l, "-deals") }, // skip duplicate promo pages
		ProductSel:  `a[title]:not([title="#"])`,
		ProductOK:   isNaivasProduct,
	})
}