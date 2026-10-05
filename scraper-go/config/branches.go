package config

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"net/url"
	"os"
	"strings"
	"sync"
)

// QuickmartBranchPresets represents predefined primary branch configurations for key regions
var QuickmartBranchPresets = map[string]map[string]interface{}{
	// Kisumu region
	"kisumu": {
		"branch_name": "Quickmart Kondele",
		"town":        "Kisumu",
		"county":      "Kisumu",
		"shop_id":     23,
		"slug":        "/2801",
		"gps_latitude": -0.0786108,
		"gps_longitude": 34.7768412,
		"address":     "Kibos Road, Kondele, Kisumu, Kenya",
		"cookies": []map[string]string{
			{"name": "_ygShopId", "value": "23"},
			{"name": "_ygGeoAddress", "value": "Kisumu"},
			{"name": "_ygGeoLat", "value": "-0.0786108"},
			{"name": "_ygGeoLng", "value": "34.7768412"},
			{"name": "_ygGeoRadius", "value": "15"},
		},
	},
	// Nairobi region (Default Flagship CBD)
	"nairobi": {
		"branch_name": "Quickmart Pioneer (CBD)",
		"town":        "Nairobi",
		"county":      "Nairobi",
		"shop_id":     16,
		"slug":        "/3501",
		"gps_latitude": -1.283698,
		"gps_longitude": 36.825346,
		"address":     "Pioneer House, Moi Avenue, Nairobi, Kenya",
		"cookies": []map[string]string{
			{"name": "_ygShopId", "value": "16"},
			{"name": "_ygGeoAddress", "value": "Nairobi"},
			{"name": "_ygGeoLat", "value": "-1.283698"},
			{"name": "_ygGeoLng", "value": "36.825346"},
			{"name": "_ygGeoRadius", "value": "15"},
		},
	},
	// Nairobi - Eastlands / Donholm
	"nairobi_donholm": {
		"branch_name": "Quickmart Donholm",
		"town":        "Nairobi",
		"county":      "Nairobi",
		"shop_id":     52,
		"slug":        "/2201",
		"gps_latitude": -1.3018395,
		"gps_longitude": 36.8885271,
		"address":     "Donholm, Nairobi, Kenya",
		"cookies": []map[string]string{
			{"name": "_ygShopId", "value": "52"},
			{"name": "_ygGeoAddress", "value": "Nairobi"},
			{"name": "_ygGeoLat", "value": "-1.3018395"},
			{"name": "_ygGeoLng", "value": "36.8885271"},
			{"name": "_ygGeoRadius", "value": "15"},
		},
	},
	// Nairobi / Kiambu - Ruaka
	"nairobi_ruaka": {
		"branch_name": "Quickmart Banana Rd",
		"town":        "Nairobi",
		"county":      "Kiambu",
		"shop_id":     65,
		"slug":        "/banana",
		"gps_latitude": -1.2056044,
		"gps_longitude": 36.7796064,
		"address":     "Banana Raini Road, Ruaka, Kenya",
		"cookies": []map[string]string{
			{"name": "_ygShopId", "value": "65"},
			{"name": "_ygGeoAddress", "value": "Ruaka"},
			{"name": "_ygGeoLat", "value": "-1.2056044"},
			{"name": "_ygGeoLng", "value": "36.7796064"},
			{"name": "_ygGeoRadius", "value": "15"},
		},
	},
	// Nairobi - Kilimani
	"nairobi_kilimani": {
		"branch_name": "Quickmart Chaka Rd",
		"town":        "Nairobi",
		"county":      "Nairobi",
		"shop_id":     14,
		"slug":        "/1801",
		"gps_latitude": -1.2915,
		"gps_longitude": 36.7865,
		"address":     "Chaka Road, Kilimani, Nairobi, Kenya",
		"cookies": []map[string]string{
			{"name": "_ygShopId", "value": "14"},
			{"name": "_ygGeoAddress", "value": "Nairobi"},
			{"name": "_ygGeoLat", "value": "-1.2915"},
			{"name": "_ygGeoLng", "value": "36.7865"},
			{"name": "_ygGeoRadius", "value": "15"},
		},
	},
	// Nakuru region
	"nakuru": {
		"branch_name": "Quickmart Nakuru Statehouse",
		"town":        "Nakuru",
		"county":      "Nakuru",
		"shop_id":     67,
		"slug":        "/nakurustatehouse",
		"gps_latitude": -0.3030988,
		"gps_longitude": 36.080026,
		"address":     "Statehouse Road, Nakuru, Kenya",
		"cookies": []map[string]string{
			{"name": "_ygShopId", "value": "67"},
			{"name": "_ygGeoAddress", "value": "Nakuru"},
			{"name": "_ygGeoLat", "value": "-0.3030988"},
			{"name": "_ygGeoLng", "value": "36.080026"},
			{"name": "_ygGeoRadius", "value": "15"},
		},
	},
	// Coastal / Mombasa region
	"mombasa": {
		"branch_name": "Quickmart Mtwapa Mall",
		"town":        "Mombasa",
		"county":      "Kilifi",
		"shop_id":     35,
		"slug":        "/4801",
		"gps_latitude": -3.9455956,
		"gps_longitude": 39.7452844,
		"address":     "Mtwapa Mall, Mombasa, Kenya",
		"cookies": []map[string]string{
			{"name": "_ygShopId", "value": "35"},
			{"name": "_ygGeoAddress", "value": "Mtwapa"},
			{"name": "_ygGeoLat", "value": "-3.9455956"},
			{"name": "_ygGeoLng", "value": "39.7452844"},
			{"name": "_ygGeoRadius", "value": "15"},
		},
	},
}

// DiscoveredBranches holds dynamically discovered branches from JSON file
var DiscoveredBranches []map[string]interface{}

// DynamicBranchCache caches resolved branch profiles to avoid repeated fetching
var DynamicBranchCache = struct {
	data map[string]map[string]interface{}
	mux  sync.RWMutex
}{data: make(map[string]map[string]interface{})}

func init() {
	loadDiscoveredBranches()
}

// loadDiscoveredBranches loads discovered branches from JSON file if available
func loadDiscoveredBranches() {
	candidates := []string{
		"quickmart_branches_discovered.json",
		"/app/scraper/config/quickmart_branches_discovered.json",
		"/app/quickmart_branches_discovered.json",
	}

	for _, path := range candidates {
		if fileExists(path) {
			data, err := os.ReadFile(path)
			if err != nil {
				log.Printf("Error reading %s: %v", path, err)
				continue
			}

			var branches []map[string]interface{}
			if err := json.Unmarshal(data, &branches); err != nil {
				log.Printf("Error parsing JSON from %s: %v", path, err)
				continue
			}

			DiscoveredBranches = branches
			log.Printf("Loaded %d discovered Quickmart branches from %s", len(branches), path)
			return
		}
	}

	log.Println("No discovered branches file found, using only presets")
}

// fileExists checks if a file exists
func fileExists(filename string) bool {
	info, err := os.Stat(filename)
	if os.IsNotExist(err) {
		return false
	}
	return err == nil
}

// fetchDynamicBranchProfile fetches live Growcer cookies and coordinates for a discovered branch slug
func fetchDynamicBranchProfile(discoveredEntry map[string]interface{}) map[string]interface{} {
	slug, _ := discoveredEntry["slug"].(string)
	name, _ := discoveredEntry["name"].(string)
	tags := discoveredEntry["location_tags"].([]interface{})

	town := "Nairobi"
	county := "Nairobi"
	if len(tags) > 0 {
		if tagStr, ok := tags[0].(string); ok {
			town = tagStr
		}
		if len(tags) > 1 {
			if tagStr, ok := tags[1].(string); ok {
				county = tagStr
			}
		}
	}

	shopIDFloat, _ := discoveredEntry["shop_id"].(float64)
	shopID := int(shopIDFloat)

	cookies := []map[string]string{}
	var lat *float64
	var lng *float64
	address := fmt.Sprintf("%s, %s, Kenya", name, town)

	// Fetch live cookies from the branch URL
	fullURL := fmt.Sprintf("https://www.quickmart.co.ke%s", slug)
	req, err := http.NewRequest("GET", fullURL, nil)
	if err != nil {
		log.Printf("Error creating request for %s: %v", fullURL, err)
	} else {
		req.Header.Set("User-Agent", "PricePoa Scraper (+https://pricepoa.co.ke)")
		client := &http.Client{Timeout: 10 * time.Second}
		resp, err := client.Do(req)
		if err != nil {
			log.Printf("Error fetching dynamic cookies for %s (%s): %v", name, slug, err)
		} else {
			defer resp.Body.Close()
			for _, cookie := range resp.Cookies() {
				if strings.HasPrefix(cookie.Name, "_yg") || cookie.Name == "PHPSESSID" {
					cookies = append(cookies, map[string]string{"name": cookie.Name, "value": cookie.Value})
					if cookie.Name == "_ygGeoLat" {
						if latVal, err := strconv.ParseFloat(cookie.Value, 64); err == nil {
							lat = &latVal
						}
					}
					if cookie.Name == "_ygGeoLng" {
						if lngVal, err := strconv.ParseFloat(cookie.Value, 64); err == nil {
							lng = &lngVal
						}
					}
					if cookie.Name == "_ygShopId" {
						if shopIDVal, err := strconv.Atoi(cookie.Value); err == nil {
							shopID = shopIDVal
						}
					}
					if cookie.Name == "_ygGeoAddress" {
						address = fmt.Sprintf("%s, Kenya", cookie.Value)
					}
				}
			}
		}
	}

	// Build the profile
	profile := map[string]interface{}{
		"branch_name": name,
		"branch":      name,
		"town":        town,
		"county":      county,
		"shop_id":     shopID,
		"slug":        slug,
		"gps_latitude": lat,
		"gps_longitude": lng,
		"address":     address,
		"cookies":     cookies,
	}

	return profile
}

// ResolveBranch resolves a branch configuration by town or branch name
func ResolveBranch(town string, branch string) map[string]interface{} {
	// 1. Match by branch name/keyword in presets
	if branch != "" {
		branchLower := strings.ToLower(strings.TrimSpace(branch))
		for key, config := range QuickmartBranchPresets {
			branchNameLower := strings.ToLower(config["branch_name"].(string))
			keyLower := strings.ToLower(key)
			if strings.Contains(branchNameLower, branchLower) || strings.Contains(keyLower, branchLower) {
				log.Printf("Resolved Quickmart branch by preset name: '%s' -> %s", branch, config["branch_name"])
				res := copyMap(config)
				res["branch"] = res["branch_name"]
				return res
			}
		}
	}

	// 2. Match by town in presets
	if town != "" {
		townLower := strings.ToLower(strings.TrimSpace(town))
		if config, exists := QuickmartBranchPresets[townLower]; exists {
			log.Printf("Resolved Quickmart branch by preset town: '%s' -> %s", town, config["branch_name"])
			res := copyMap(config)
			res["branch"] = res["branch_name"]
			return res
		}

		for _, config := range QuickmartBranchPresets {
			configTownLower := strings.ToLower(config["town"].(string))
			if strings.Contains(configTownLower, townLower) {
				log.Printf("Resolved Quickmart branch by preset partial town: '%s' -> %s", town, config["branch_name"])
				res := copyMap(config)
				res["branch"] = res["branch_name"]
				return res
			}
		}
	}

	// 3. Dynamic lookup across all discovered branches
	query := ""
	if branch != "" {
		query = strings.ToLower(strings.TrimSpace(branch))
	} else if town != "" {
		query = strings.ToLower(strings.TrimSpace(town))
	}
	if query != "" {
		// Check dynamic cache first
		DynamicBranchCache.mux.RLock()
		if cached, found := DynamicBranchCache.data[query]; found {
			DynamicBranchCache.mux.RUnlock()
			return copyMap(cached)
		}
		DynamicBranchCache.mux.RUnlock()

		for _, entry := range DiscoveredBranches {
			bName, _ := entry["name"].(string)
			bSlug, _ := entry["slug"].(string)
			bTags := entry["location_tags"].([]interface{})

			bNameLower := strings.ToLower(bName)
			bSlugLower := strings.ToLower(bSlug)
			bTagsStr := strings.ToLower(strings.Join(interfaceSliceToStringSlice(bTags), " "))

			if strings.Contains(bNameLower, query) || strings.Contains(bSlugLower, query) || strings.Contains(bTagsStr, query) {
				log.Printf("Dynamically resolving discovered branch for '%s': %s", query, bName)
				profile := fetchDynamicBranchProfile(entry)
				DynamicBranchCache.mux.Lock()
				DynamicBranchCache.data[query] = profile
				DynamicBranchCache.mux.Unlock()
				return copyMap(profile)
			}
		}
	}

	// 4. Default fallback: Nairobi CBD
	log.Println("No branch or town matched, falling back to default Quickmart Nairobi Pioneer")
	result := copyMap(QuickmartBranchPresets["nairobi"])
	result["branch"] = result["branch_name"]
	return result
}

// copyMap creates a deep copy of a map[string]interface{}
func copyMap(source map[string]interface{}) map[string]interface{} {
	dest := make(map[string]interface{}, len(source))
	for k, v := range source {
		switch vv := v.(type) {
		case map[string]interface{}:
			dest[k] = copyMap(vv)
		case []interface{}:
			if vv != nil {
				dest[k] = copySlice(vv)
			} else {
				dest[k] = vv
			}
		default:
			dest[k] = vv
		}
	}
	return dest
}

// copySlice creates a deep copy of a []interface{}
func copySlice(source []interface{}) []interface{} {
	dest := make([]interface{}, len(source))
	for i, v := range source {
		switch vv := v.(type) {
		case map[string]interface{}:
			dest[i] = copyMap(vv)
		case []interface{}:
			if vv != nil {
				dest[i] = copySlice(vv)
			} else {
				dest[i] = vv
			}
		default:
			dest[i] = vv
		}
	}
	return dest
}

// interfaceSliceToStringSlice converts []interface{} to []string, ignoring non-string elements
func interfaceSliceToStringSlice(source []interface{}) []string {
	var result []string
	for _, v := range source {
		if str, ok := v.(string); ok {
			result = append(result, str)
		}
	}
	return result
}

// ListAvailableBranches lists all available predefined branch configurations
func ListAvailableBranches() []map[string]interface{} {
	result := make([]map[string]interface{}, 0, len(QuickmartBranchPresets))
	for _, config := range QuickmartBranchPresets {
		result = append(result, copyMap(config))
	}
	return result
}

// ListAllBranches lists all discovered branches (presets + discovered)
func ListAllBranches() []map[string]interface{} {
	if len(DiscoveredBranches) > 0 {
		result := make([]map[string]interface{}, 0, len(DiscoveredBranches))
		for _, branch := range DiscoveredBranches {
			result = append(result, copyMap(branch))
		}
		return result
	}
	return ListAvailableBranches()
}