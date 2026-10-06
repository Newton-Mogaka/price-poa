package scraper

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/url"
	"strings"
	"time"

	"github.com/PuerkitoBio/goquery"
	"github.com/chromedp/chromedp"
	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
)

// StoreConfig describes one store. Each spider fills this in and calls RunStore.
type StoreConfig struct {
	Chain  string // e.g. "Naivas"
	Branch string // e.g. "Online Store"
	Source string // e.g. "naivas_online"

	StartURL string // homepage, or the category page itself when CategorySel is ""

	// Category discovery. Leave CategorySel empty to treat StartURL as the only category page.
	CategorySel   string
	CategoryOK    func(link string) bool
	FixedCategory string // if set, every product gets this category name

	// Product discovery on category pages.
	ProductSel string
	ProductOK  func(link string) bool
	NextSel    string // pagination "next" link selector; empty = no pagination

	// Extra selectors, tried before the defaults.
	NameSels  []string
	PriceSels []string
	PromoSels []string
	WasSel    string // defaults to ".price-was"
	NowSel    string // defaults to ".price-current"

	// Prepare runs inside the browser tab before each navigation (e.g. to set cookies).
	Prepare func(ctx context.Context) error

	// Extra fields merged into every product document.
	Extra bson.M
}

var (
	defaultNameSels  = []string{`h1[data-testid="product-title"]`, `[data-testid="product-title"]`, `.product-title`, `.product-name`, `h1`}
	defaultPriceSels = []string{`[data-testid="price"]`, `.price-current`, `.price-sale`, `.price`, `[class*="price"]`, `.cost`}
	defaultPromoSels = []string{`.badge-sale`, `.label-offer`, `.promo-tag`, `[data-testid="price-original"]`, `.price-was`, `.original-price`}
)

// RunStore scrapes one store end to end and inserts the products into MongoDB.
func RunStore(ctx context.Context, coll *mongo.Collection, cfg StoreConfig) {
	log.Printf("Running %s spider", cfg.Chain)

	browserCtx, cancel := newBrowserContext(ctx)
	defer cancel()

	// Start the browser once; every tab below shares it.
	if err := chromedp.Run(browserCtx); err != nil {
		log.Printf("Failed to start browser for %s: %v", cfg.Chain, err)
		return
	}

	var categories []string
	if cfg.CategorySel == "" {
		categories = []string{cfg.StartURL}
	} else {
		html, err := fetchHTML(browserCtx, cfg, cfg.StartURL)
		if err != nil {
			log.Printf("Failed to fetch %s homepage: %v", cfg.Chain, err)
			return
		}
		categories = linksFrom(html, cfg.StartURL, cfg.CategorySel, cfg.CategoryOK)
		log.Printf("Found %d category links on %s homepage", len(categories), cfg.Chain)
	}

	var products []bson.M
	for _, categoryURL := range categories {
		category := cfg.FixedCategory
		if category == "" {
			category = categoryFromURL(categoryURL)
		}
		products = append(products, scrapeCategory(browserCtx, cfg, categoryURL, category)...)
		time.Sleep(1 * time.Second)
	}

	if len(products) == 0 {
		log.Printf("No products extracted from %s", cfg.Chain)
		return
	}

	docs := make([]interface{}, 0, len(products))
	for _, p := range products {
		docs = append(docs, p)
	}
	result, err := coll.InsertMany(ctx, docs, options.InsertMany().SetOrdered(false))
	if err != nil {
		log.Printf("Failed to insert %s products: %v", cfg.Chain, err)
		return
	}
	log.Printf("Inserted %d products from %s", len(result.InsertedIDs), cfg.Chain)
}

// ---------- browser ----------

func newBrowserContext(parent context.Context) (context.Context, context.CancelFunc) {
	opts := append(chromedp.DefaultExecAllocatorOptions[:],
		chromedp.Flag("headless", true),
		chromedp.Flag("no-sandbox", true),
		chromedp.Flag("disable-gpu", true),
		chromedp.Flag("disable-dev-shm-usage", true),
	)
	allocCtx, cancelAlloc := chromedp.NewExecAllocator(parent, opts...)
	ctx, cancelCtx := chromedp.NewContext(allocCtx)
	return ctx, func() {
		cancelCtx()
		cancelAlloc()
	}
}

// fetchHTML opens a fresh tab, loads pageURL and returns the rendered HTML.
func fetchHTML(browserCtx context.Context, cfg StoreConfig, pageURL string) (string, error) {
	tabCtx, cancelTab := chromedp.NewContext(browserCtx)
	defer cancelTab()
	runCtx, cancelRun := context.WithTimeout(tabCtx, 30*time.Second)
	defer cancelRun()

	var html string
	var actions []chromedp.Action
	if cfg.Prepare != nil {
		actions = append(actions, chromedp.ActionFunc(cfg.Prepare))
	}
	actions = append(actions,
		chromedp.Navigate(pageURL),
		chromedp.WaitReady("body"),
		chromedp.OuterHTML("html", &html),
	)
	if err := chromedp.Run(runCtx, actions...); err != nil {
		return "", err
	}
	return html, nil
}

// ---------- category + product discovery ----------

func scrapeCategory(browserCtx context.Context, cfg StoreConfig, categoryURL, category string) []bson.M {
	var products []bson.M
	visited := make(map[string]bool)
	currentURL := categoryURL

	for pageNum := 1; currentURL != "" && !visited[currentURL]; pageNum++ {
		visited[currentURL] = true
		log.Printf("Scraping %s category page %d: %s", cfg.Chain, pageNum, currentURL)

		pageHTML, err := fetchHTML(browserCtx, cfg, currentURL)
		if err != nil {
			log.Printf("Failed to fetch %s category page %s: %v", cfg.Chain, currentURL, err)
			break
		}

		productLinks := linksFrom(pageHTML, currentURL, cfg.ProductSel, cfg.ProductOK)
		log.Printf("Found %d product links on page %d", len(productLinks), pageNum)

		for _, link := range productLinks {
			if p := scrapeProduct(browserCtx, cfg, link, category); p != nil {
				products = append(products, p)
			}
			time.Sleep(300 * time.Millisecond)
		}

		currentURL = nextPageLink(pageHTML, currentURL, cfg.NextSel)
		time.Sleep(2 * time.Second)
	}
	return products
}

func scrapeProduct(browserCtx context.Context, cfg StoreConfig, productURL, category string) bson.M {
	html, err := fetchHTML(browserCtx, cfg, productURL)
	if err != nil {
		log.Printf("Failed to fetch product page %s: %v", productURL, err)
		return nil
	}
	doc, err := goquery.NewDocumentFromReader(strings.NewReader(html))
	if err != nil {
		log.Printf("Failed to parse product page %s: %v", productURL, err)
		return nil
	}
	if p := parseJSONLD(doc, cfg, productURL, category); p != nil {
		return p
	}
	return parseCSS(doc, cfg, productURL, category)
}

// linksFrom returns unique, absolute links matching selector that pass ok (ok may be nil).
func linksFrom(html, baseURL, selector string, ok func(string) bool) []string {
	doc, err := goquery.NewDocumentFromReader(strings.NewReader(html))
	if err != nil {
		log.Printf("Error parsing HTML: %v", err)
		return nil
	}
	seen := make(map[string]bool)
	var links []string
	doc.Find(selector).Each(func(_ int, s *goquery.Selection) {
		href, exists := s.Attr("href")
		if !exists {
			return
		}
		link := resolveURL(baseURL, href)
		if link == "" || seen[link] {
			return
		}
		if ok != nil && !ok(link) {
			return
		}
		seen[link] = true
		links = append(links, link)
	})
	return links
}

func nextPageLink(html, baseURL, selector string) string {
	if selector == "" {
		return ""
	}
	doc, err := goquery.NewDocumentFromReader(strings.NewReader(html))
	if err != nil {
		return ""
	}
	href, ok := doc.Find(selector).First().Attr("href")
	if !ok {
		return ""
	}
	return resolveURL(baseURL, href)
}

// resolveURL makes href absolute against base. Returns "" for non-http(s) links.
func resolveURL(base, href string) string {
	b, err := url.Parse(base)
	if err != nil {
		return ""
	}
	u, err := url.Parse(strings.TrimSpace(href))
	if err != nil {
		return ""
	}
	r := b.ResolveReference(u)
	if r.Scheme != "http" && r.Scheme != "https" {
		return ""
	}
	r.Fragment = ""
	return r.String()
}

// categoryFromURL: https://x.com/category/dairy-eggs -> "Dairy Eggs".
func categoryFromURL(link string) string {
	for _, marker := range []string{"/category/", "/collections/", "/shop/"} {
		if idx := strings.LastIndex(link, marker); idx != -1 {
			rest := link[idx+len(marker):]
			if end := strings.IndexAny(rest, "/?#"); end != -1 {
				rest = rest[:end]
			}
			if rest != "" {
				return strings.Title(strings.ReplaceAll(rest, "-", " "))
			}
		}
	}
	return "General"
}

// ---------- product parsing ----------

func parseJSONLD(doc *goquery.Document, cfg StoreConfig, productURL, category string) bson.M {
	var result bson.M

	doc.Find(`script[type="application/ld+json"]`).EachWithBreak(func(_ int, s *goquery.Selection) bool {
		var data interface{}
		if err := json.Unmarshal([]byte(s.Text()), &data); err != nil {
			return true
		}

		var items []interface{}
		switch v := data.(type) {
		case []interface{}:
			items = v
		case map[string]interface{}:
			items = []interface{}{v}
		default:
			return true
		}

		for _, item := range items {
			m, ok := item.(map[string]interface{})
			if !ok || !strings.Contains(fmt.Sprint(m["@type"]), "Product") {
				continue
			}
			name, _ := m["name"].(string)
			name = strings.TrimSpace(name)
			if name == "" {
				continue
			}
			offer := ldOffer(m)
			if offer == nil {
				continue
			}
			price := ""
			switch v := offer["price"].(type) {
			case string:
				price = parsePriceText(v)
			case float64:
				price = fmt.Sprintf("%.2f", v)
			}
			if price == "" {
				continue
			}
			// JSON-LD doesn't reliably show promotions; the CSS path handles was/now pricing.
			result = buildProduct(cfg, name, price, false, "", productURL, category)
			return false
		}
		return true
	})

	return result
}

func parseCSS(doc *goquery.Document, cfg StoreConfig, productURL, category string) bson.M {
	nameSels := append(append([]string{}, cfg.NameSels...), defaultNameSels...)
	priceSels := append(append([]string{}, cfg.PriceSels...), defaultPriceSels...)
	promoSels := append(append([]string{}, cfg.PromoSels...), defaultPromoSels...)

	productName := firstText(doc, nameSels...)
	priceText := firstText(doc, priceSels...)
	if productName == "" || priceText == "" {
		log.Printf("Could not extract product name or price from %s", productURL)
		return nil
	}

	price := parsePriceText(priceText)
	if price == "" {
		log.Printf("Could not parse price %q from %s", priceText, productURL)
		return nil
	}

	isPromotional := false
	promotionDetails := ""
	if promo := firstText(doc, promoSels...); promo != "" {
		isPromotional = true
		promotionDetails = promo
	}

	if !isPromotional {
		wasSel, nowSel := cfg.WasSel, cfg.NowSel
		if wasSel == "" {
			wasSel = ".price-was"
		}
		if nowSel == "" {
			nowSel = ".price-current"
		}
		was, now := firstText(doc, wasSel), firstText(doc, nowSel)
		if was != "" && now != "" {
			isPromotional = true
			promotionDetails = fmt.Sprintf("Was %s, now %s", was, now)
		}
	}

	return buildProduct(cfg, productName, price, isPromotional, promotionDetails, productURL, category)
}

func buildProduct(cfg StoreConfig, name, price string, promo bool, promoDetails, productURL, category string) bson.M {
	now := time.Now()
	p := bson.M{
		"product_name":      strings.TrimSpace(name),
		"store_chain":       cfg.Chain,
		"store_branch":      cfg.Branch,
		"price_kes":         price,
		"currency":          "KES",
		"source":            cfg.Source,
		"is_promotional":    promo,
		"promotion_details": promoDetails,
		"category":          category,
		"response_url":      productURL,
		"verified_at":       now,
		"created_at":        now,
		"scraper":           "go",
	}
	for k, v := range cfg.Extra {
		p[k] = v
	}
	return p
}

// ---------- small helpers ----------

// firstText returns the trimmed text of the first selector that matches non-empty text.
func firstText(doc *goquery.Document, selectors ...string) string {
	for _, sel := range selectors {
		if txt := strings.TrimSpace(doc.Find(sel).First().Text()); txt != "" {
			return txt
		}
	}
	return ""
}

// parsePriceText pulls the first number out of text like "KES 1,299.00" -> "1299.00".
func parsePriceText(s string) string {
	var b strings.Builder
	started := false
	for _, r := range s {
		switch {
		case r >= '0' && r <= '9':
			started = true
			b.WriteRune(r)
		case r == '.' && started:
			b.WriteRune(r)
		case r == ',' && started:
			// thousands separator
		default:
			if started {
				return strings.TrimRight(b.String(), ".")
			}
		}
	}
	return strings.TrimRight(b.String(), ".")
}

func ldOffer(m map[string]interface{}) map[string]interface{} {
	switch o := m["offers"].(type) {
	case map[string]interface{}:
		return o
	case []interface{}:
		if len(o) > 0 {
			if first, ok := o[0].(map[string]interface{}); ok {
				return first
			}
		}
	}
	return nil
}