package spiders

import (
	"context"
	"fmt"
	"log"
	"strconv"
	"strings"

	"github.com/chromedp/cdproto/network"
	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/mongo"

	"github.com/pricepoa/scraper-go/config"
	"github.com/pricepoa/scraper-go/scraper"
)

// --- tolerant readers for the branch profile map (missing keys give zero values, never a panic) ---

func mapString(m map[string]interface{}, key string) string {
	if v, ok := m[key].(string); ok {
		return v
	}
	return ""
}

func mapInt(m map[string]interface{}, key string) int {
	switch v := m[key].(type) {
	case int:
		return v
	case int32:
		return int(v)
	case int64:
		return int(v)
	case float64:
		return int(v)
	}
	return 0
}

func mapFloatPtr(m map[string]interface{}, key string) *float64 {
	switch v := m[key].(type) {
	case *float64:
		return v
	case float64:
		return &v
	}
	return nil
}

// RunQuickmartSpider scrapes Quickmart for the branch resolved from town/branch.
func RunQuickmartSpider(ctx context.Context, pricesColl *mongo.Collection, town string, branch string) {
	profile := config.ResolveBranch(town, branch)

	storeBranch := mapString(profile, "branch_name")
	storeTown := mapString(profile, "town")
	storeCounty := mapString(profile, "county")
	address := mapString(profile, "address")
	shopID := mapInt(profile, "shop_id")
	gpsLat := mapFloatPtr(profile, "gps_latitude")
	gpsLng := mapFloatPtr(profile, "gps_longitude")

	log.Printf("Running Quickmart spider for branch '%s' in %s, %s (Shop ID: %d)",
		storeBranch, storeTown, storeCounty, shopID)

	// Branch cookies, set in the browser tab before every navigation.
	prepare := func(ctx context.Context) error {
		cookies := map[string]string{
			"_ygShopId":     strconv.Itoa(shopID),
			"_ygGeoAddress": storeTown,
			"_ygGeoRadius":  "15",
		}
		if gpsLat != nil {
			cookies["_ygGeoLat"] = fmt.Sprintf("%f", *gpsLat)
		}
		if gpsLng != nil {
			cookies["_ygGeoLng"] = fmt.Sprintf("%f", *gpsLng)
		}
		for name, value := range cookies {
			if err := network.SetCookie(name, value).WithURL("https://www.quickmart.co.ke/").Do(ctx); err != nil {
				return err
			}
		}
		return nil
	}

	scraper.RunStore(ctx, pricesColl, scraper.StoreConfig{
		Chain:  "Quickmart",
		Branch: storeBranch,
		Source: "quickmart_online",

		StartURL:    "https://www.quickmart.co.ke/",
		CategorySel: `.category-menu-link.categoryMenuLinkJs[href]`,
		CategoryOK:  func(l string) bool { return strings.Contains(l, "/category/") },
		ProductSel:  `a.products-title[href]`,
		ProductOK: func(l string) bool {
			return strings.Contains(l, "/product/") || strings.Contains(l, "/products/")
		},
		NextSel: `a[rel="next"], a.next-page, .next-page a, a.pagination__next, .pagination__next a`,

		NameSels:  []string{`h1.product-title`},
		PriceSels: []string{`.products-price-new`, `.products-price`, `.price-new`, `.product-price`, `.current-price`, `.sale-price`},
		PromoSels: []string{`.products-price-old`, `.products-price-off`, `.badge-offer, .label-sale, .promo-badge`, `[data-testid="original-price"]`, `.was-price`},
		WasSel:    ".products-price-old",
		NowSel:    ".products-price-new",

		Prepare: prepare,
		Extra: bson.M{
			"store_town":    storeTown,
			"store_county":  storeCounty,
			"gps_latitude":  gpsLat,
			"gps_longitude": gpsLng,
			"address":       address,
		},
	})
}