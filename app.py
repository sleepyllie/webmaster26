"""
Community Resource Hub - Northern Alabama
==========================================
Flask backend serving HTML templates with jQuery frontend.

APIs used:
  - Geoapify Places API  (local resources by location — requires free key)
  - Geoapify Place Details API (enriched place information)
  - AI Description Generation (Groq — FREE, for enriching sparse data)
  - ProPublica Nonprofit Explorer (nonprofits — no key needed)
  - Pinned seed data (guaranteed local fallback)
"""

from flask import Flask, render_template, request, jsonify
import requests
import json
import os
import re
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, as_completed


app = Flask(__name__,
    template_folder="templates",
    static_folder="static"
)

# ---------------------------------------------------------------------------
# API Keys (hardcoded)
# ---------------------------------------------------------------------------
GEOAPIFY_KEY = os.getenv("GEOAPIFY_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# ---------------------------------------------------------------------------
# File paths
# ---------------------------------------------------------------------------
IS_VERCEL = os.environ.get("VERCEL", False)
BASE_DIR = os.path.dirname(__file__)
READ_DATA_DIR = os.path.join(BASE_DIR, "data")  # For reading seed data (spotlights, etc.)
WRITE_DATA_DIR = "/tmp" if IS_VERCEL else os.path.join(BASE_DIR, "data")  # For writing cache

# Read-only files (shipped with app)
SPOTS_FILE = os.path.join(READ_DATA_DIR, "spotlights.json")

# Writable files (cache, user submissions)
USER_FILE = os.path.join(WRITE_DATA_DIR, "user_resources.json")
CONTACT_FILE = os.path.join(WRITE_DATA_DIR, "contact_messages.json")
CACHE_FILE = os.path.join(WRITE_DATA_DIR, "description_cache.json")

# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def read_json(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)

def write_json(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[Write] Could not write to {path}: {e}")

# Description cache for AI-generated descriptions
_description_cache = {}

def load_description_cache():
    global _description_cache
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE) as f:
                _description_cache = json.load(f)
        except:
            _description_cache = {}

def save_description_cache():
    write_json(CACHE_FILE, _description_cache)

def get_cached_description(key):
    return _description_cache.get(key)

def clear_description_cache():
    """Clear all cached descriptions."""
    global _description_cache
    old_count = len(_description_cache)
    _description_cache = {}
    if os.path.exists(CACHE_FILE):
        os.remove(CACHE_FILE)
    return old_count

def set_cached_description(key, description):
    _description_cache[key] = description
    # Save periodically (every 10 new entries)
    if len(_description_cache) % 10 == 0:
        save_description_cache()

# Load cache on startup
load_description_cache()

# ---------------------------------------------------------------------------
# Category map — maps keywords → our display categories
# ---------------------------------------------------------------------------

CATEGORY_KEYWORDS = {
    "Healthcare":            ["health", "hospital", "clinic", "medical", "dental", "pharmacy", "urgent care", "doctor"],
    "Mental Health":         ["mental", "counseling", "therapy", "behavioral", "psychiatric", "substance", "addiction", "recovery"],
    "Food & Agriculture":    ["food", "hunger", "meal", "soup", "pantry", "nutrition", "grocery", "farm"],
    "Housing & Shelter":     ["housing", "shelter", "homeless", "transitional", "rent", "eviction", "habitat"],
    "Education":             ["education", "school", "library", "literacy", "tutoring", "college", "youth program", "after school", "classical", "academy", "learning"],
    "Youth Development":     ["youth", "children", "kids", "boys", "girls", "teen", "camp", "scout"],
    "Human Services":        ["social service", "family", "veteran", "senior", "elderly", "disability", "welfare", "united way"],
    "Animal Welfare":        ["animal", "pet", "shelter", "spay", "neuter", "rescue", "humane"],
    "Arts & Culture":        ["art", "music", "theater", "museum", "culture", "perform", "gallery", "dance"],
    "Community Development": ["community", "neighborhood", "development", "civic", "volunteer", "association"],
    "Employment":            ["employment", "job", "workforce", "career", "training", "resume", "hire"],
    "Crime & Legal":         ["legal", "law", "court", "crime", "justice", "attorney", "domestic violence"],
    "Environment":           ["environment", "conservation", "green", "recycle", "nature", "park", "trail"],
    "Recreation & Sports":   ["recreation", "sport", "gym", "fitness", "park", "ymca", "pool"],
    "Public Safety":         ["fire", "police", "emergency", "disaster", "safety", "rescue"],
    "Religion":              ["church", "mosque", "synagogue", "temple", "faith", "ministry", "worship"],
    "Civil Rights":          ["civil rights", "equity", "equality", "advocacy", "immigrant", "refugee"],
    "Public Policy":         ["policy", "government", "civic", "vote", "election", "public interest"],
}

ALL_CATEGORIES = sorted(CATEGORY_KEYWORDS.keys())

def guess_category(text):
    """Guess a display category from free text (name + description)."""
    t = (text or "").lower()
    for cat, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in t for kw in keywords):
            return cat
    return "Community Development"

# ---------------------------------------------------------------------------
# Geographic scope — North & Mid Alabama
# ---------------------------------------------------------------------------

ALABAMA_CITIES = {
    "huntsville", "madison", "athens", "decatur", "florence",
    "muscle shoals", "sheffield", "tuscumbia", "scottsboro",
    "fort payne", "albertville", "guntersville", "arab",
    "hartselle", "cullman", "boaz", "rainsville", "fyffe",
    "russellville", "moulton", "rogersville", "ardmore",
    "hazel green", "harvest", "meridianville", "owens cross roads",
    "new market", "toney", "laceys spring", "somerville",
    "birmingham", "hoover", "vestavia hills", "homewood",
    "mountain brook", "bessemer", "tuscaloosa", "northport",
    "jasper", "anniston", "oxford", "gadsden", "talladega",
    "sylacauga", "alexander city", "oneonta", "pell city",
    "gardendale", "center point", "trussville", "moody",
}

ALABAMA_ZIP_PREFIXES = (
    "356", "357", "358", "359", "354", "355",
    "350", "351", "352", "360", "361", "362", "363",
)

def is_alabama_location(location_str):
    if not location_str:
        return True
    loc = location_str.lower().strip()
    has_state = ", al" in loc or ", alabama" in loc or loc.endswith(" al") or loc.endswith(" alabama")
    other_states = [", ga", ", tn", ", ms", ", fl", ", tx", ", ca", ", ny", ", nc", ", sc"]
    if not has_state and any(s in loc for s in other_states):
        return False
    for city in ALABAMA_CITIES:
        if city in loc:
            return True
    m = re.search(r'\b(\d{5})\b', loc)
    if m:
        return m.group(1).startswith(ALABAMA_ZIP_PREFIXES)
    return True

# ---------------------------------------------------------------------------
# AI Description Generation (OpenAI or Groq)
# ---------------------------------------------------------------------------

def generate_ai_description(name, category, address, existing_info=""):
    """
    Generate a rich, informative description using AI.
    Falls back to a template if no AI key is available.
    """
    cache_key = f"{name}|{category}|{address}"
    cached = get_cached_description(cache_key)
    if cached:
        return cached
    
    # Prepare context
    context_parts = [f"Name: {name}", f"Category: {category}"]
    if address:
        context_parts.append(f"Location: {address}")
    if existing_info:
        context_parts.append(f"Known info: {existing_info}")
    context = "\n".join(context_parts)
    
    prompt = f"""Write a helpful 1-2 sentence description for this community resource in Northern Alabama. Be specific about what services or programs they likely offer based on their name and category. Do not make up specific facts like hours or phone numbers.

{context}

Description:"""

    # Use Groq (free API)
    description = None
    
    if GROQ_API_KEY:
        print(f"[Groq AI] Generating description for: {name}")
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "llama-3.1-8b-instant",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 100,
                    "temperature": 0.7
                },
                timeout=5
            )
            if resp.status_code == 200:
                description = resp.json()["choices"][0]["message"]["content"].strip()
                print(f"[Groq AI] Success: {description[:50]}...")
            else:
                print(f"[Groq AI] API returned {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            print(f"[Groq AI] Error: {e}")
    
    # Fallback: Generate a better template-based description
    if not description:
        if not GROQ_API_KEY:
            print(f"[Groq AI] No API key set - using template for: {name}")
        else:
            print(f"[Groq AI] API call failed - using template for: {name}")
        description = generate_template_description(name, category, address)
    
    # Cache the result
    set_cached_description(cache_key, description)
    return description


def generate_template_description(name, category, address):
    """Generate a better template-based description when AI is unavailable."""
    city = ""
    if address:
        # Extract city from address
        parts = address.split(",")
        if len(parts) >= 2:
            city = parts[-2].strip() if len(parts) >= 2 else parts[0].strip()
        else:
            city = address.strip()
    
    location_phrase = f"in {city}" if city else "in Northern Alabama"
    
    # Category-specific templates
    templates = {
        "Healthcare": f"Healthcare facility {location_phrase} providing medical services and care to the community.",
        "Mental Health": f"Mental health and counseling services {location_phrase}, offering support for individuals and families.",
        "Food & Agriculture": f"Food assistance resource {location_phrase}, helping address hunger and food insecurity in the community.",
        "Housing & Shelter": f"Housing and shelter services {location_phrase}, providing support for those in need of stable housing.",
        "Education": f"Educational institution {location_phrase} dedicated to learning and academic development.",
        "Youth Development": f"Youth-focused organization {location_phrase} providing programs and activities for young people.",
        "Human Services": f"Human services organization {location_phrase} connecting residents with vital support and resources.",
        "Animal Welfare": f"Animal welfare organization {location_phrase} dedicated to the care and protection of animals.",
        "Arts & Culture": f"Arts and cultural organization {location_phrase} enriching the community through creative programming.",
        "Community Development": f"Community organization {location_phrase} working to strengthen and support local neighborhoods.",
        "Employment": f"Employment and workforce services {location_phrase}, helping residents find jobs and develop careers.",
        "Crime & Legal": f"Legal services and advocacy {location_phrase}, providing assistance with civil and legal matters.",
        "Environment": f"Environmental organization {location_phrase} focused on conservation and sustainability.",
        "Recreation & Sports": f"Recreation and sports facility {location_phrase} promoting active lifestyles and community engagement.",
        "Public Safety": f"Public safety organization {location_phrase} serving and protecting the community.",
        "Religion": f"Faith-based organization {location_phrase} serving the spiritual needs of the community.",
        "Civil Rights": f"Civil rights and advocacy organization {location_phrase} working for equity and justice.",
        "Public Policy": f"Public policy organization {location_phrase} engaged in civic and governmental affairs.",
    }
    
    return templates.get(category, f"Community resource {location_phrase} serving local residents.")


# ---------------------------------------------------------------------------
# Geoapify Places API — local resources near Huntsville
# ---------------------------------------------------------------------------

# Huntsville, AL coordinates
HUNTSVILLE_LAT = 34.7304
HUNTSVILLE_LON = -86.5861
SEARCH_RADIUS_M = 50000  # 50km covers North/Mid Alabama

# Geoapify categories that map to community resources
GEOAPIFY_CATEGORIES = [
    "healthcare",
    "healthcare.hospital",
    "healthcare.clinic_or_praxis",
    "healthcare.pharmacy",
    "education",
    "education.school",
    "education.library",
    "entertainment.culture",
    "entertainment.museum",
    "religion.place_of_worship",
    "sport.sports_centre",
    "sport.fitness.fitness_centre",
    "office.government.social_services",
    "office.government.public_service",
    "office.non_profit",
    "office.charity",
    "office.foundation",
    "office.association",
    "office.employment_agency",
    "service.social_facility",
    "service.social_facility.shelter",
    "service.social_facility.food",
    "activity.community_center",
]


def fetch_geoapify_place_details(place_id):
    """
    Fetch detailed information for a specific place from Geoapify.
    Returns enriched data including hours, contact, description.
    """
    if not GEOAPIFY_KEY or not place_id:
        return None
    
    try:
        resp = requests.get(
            f"https://api.geoapify.com/v2/place-details",
            params={
                "id": place_id,
                "apiKey": GEOAPIFY_KEY,
                "lang": "en"
            },
            timeout=5
        )
        
        if resp.status_code != 200:
            return None
        
        data = resp.json()
        features = data.get("features", [])
        if not features:
            return None
        
        props = features[0].get("properties", {})
        raw = props.get("datasource", {}).get("raw", {})
        
        return {
            "description": raw.get("description") or props.get("description"),
            "phone": raw.get("phone") or props.get("contact", {}).get("phone"),
            "website": raw.get("website") or props.get("website"),
            "email": raw.get("email") or props.get("contact", {}).get("email"),
            "opening_hours": raw.get("opening_hours"),
            "wheelchair": raw.get("wheelchair"),
            "internet_access": raw.get("internet_access"),
        }
        
    except Exception as e:
        print(f"[Geoapify Details] Error: {e}")
        return None


def fetch_geoapify(query="", category="", page=0, enrich=True):
    """
    Search for places near Huntsville using Geoapify Places API.
    Returns (list_of_results, api_ok: bool).
    
    If enrich=True, will fetch additional details and AI descriptions.
    """
    if not GEOAPIFY_KEY:
        print("[Geoapify] No API key set.")
        return [], False

    # Map our display category to Geoapify categories
    geo_cat = {
        "Healthcare":            "healthcare",
        "Mental Health":         "healthcare.clinic_or_praxis",
        "Education":             "education",
        "Religion":              "religion.place_of_worship",
        "Recreation & Sports":   "sport.sports_centre",
        "Arts & Culture":        "entertainment.culture",
        "Community Development": "activity.community_center",
        "Human Services":        "service.social_facility",
        "Youth Development":     "education.school",
        "Housing & Shelter":     "service.social_facility.shelter",
        "Food & Agriculture":    "service.social_facility.food",
        "Employment":            "office.employment_agency",
        "Public Safety":         "office.government.public_service",
        "Animal Welfare":        "pet.veterinary",
        "Crime & Legal":         "office.lawyer",
        "Philanthropy":          "office.foundation",
    }.get(category, "")

    params = {
        "categories": geo_cat or ",".join(GEOAPIFY_CATEGORIES),
        "filter":     f"circle:{HUNTSVILLE_LON},{HUNTSVILLE_LAT},{SEARCH_RADIUS_M}",
        "bias":       f"proximity:{HUNTSVILLE_LON},{HUNTSVILLE_LAT}",
        "limit":      50,
        "offset":     page * 50,
        "apiKey":     GEOAPIFY_KEY,
        "lang":       "en",
    }

    # Add text filter if query provided
    if query:
        params["name"] = query

    try:
        resp = requests.get(
            "https://api.geoapify.com/v2/places",
            params=params,
            timeout=10
        )
        print(f"[Geoapify] status={resp.status_code} url={resp.url[:120]}")
        if resp.status_code != 200:
            print(f"[Geoapify] error body: {resp.text[:300]}")
            return [], False
        body = resp.json()

        results = []
        for feature in body.get("features", []):
            props = feature.get("properties", {})
            
            name = props.get("name", "").strip()
            if not name:
                continue

            addr_parts = [
                props.get("address_line1", ""),
                props.get("city", ""),
                props.get("state_code", ""),
            ]
            address = ", ".join(p for p in addr_parts if p)

            # Only keep North/Mid Alabama results
            if not is_alabama_location(address):
                continue

            combined_text = f"{name} {props.get('categories', '')} {address}"
            cat = category if category else guess_category(combined_text)
            
            # Get raw data from datasource
            raw = props.get("datasource", {}).get("raw", {})
            
            # Build initial description from available data
            existing_desc = raw.get("description", "")
            phone = raw.get("phone", "") or props.get("contact", {}).get("phone", "")
            website = props.get("website", "") or raw.get("website", "")
            opening_hours = raw.get("opening_hours", "")
            
            # Create enriched description
            if existing_desc:
                print(f"[Geoapify] Using existing description for: {name}")
                description = existing_desc
            elif enrich:
                # Generate AI description if no existing description
                print(f"[Geoapify] Enriching with AI for: {name}")
                description = generate_ai_description(name, cat, address)
            else:
                print(f"[Geoapify] Using fallback for: {name}")
                description = f"{cat} resource located in {props.get('city', 'North Alabama')}."
            
            # Add hours to description if available
            if opening_hours and opening_hours not in description:
                description += f" Hours: {opening_hours}"

            results.append({
                "name":        name,
                "category":    cat,
                "description": description,
                "address":     address,
                "phone":       phone,
                "website":     website,
                "hours":       opening_hours,
                "place_id":    props.get("place_id"),
                "source":      "places",
            })

        return results, True

    except Exception as e:
        print(f"[Geoapify error] {type(e).__name__}: {e}")
        return [], False


# ---------------------------------------------------------------------------
# Enrichment: Combine data from multiple sources
# ---------------------------------------------------------------------------

def enrich_resource(resource):
    """
    Enrich a resource with AI-generated descriptions when the existing description is sparse.
    Uses Groq (free) to generate helpful, contextual descriptions.
    """
    name = resource.get("name", "")
    address = resource.get("address", "")
    category = resource.get("category", "")
    description = resource.get("description", "")
    
    # Check if description needs enrichment
    needs_enrichment = (
        not description or 
        "resource located in" in description.lower() or
        len(description) < 50
    )
    
    if needs_enrichment:
        # Generate AI description using Groq (free)
        resource["description"] = generate_ai_description(name, category, address)
    
    return resource


# ---------------------------------------------------------------------------
# ProPublica Nonprofit Explorer — free, no key required
# ---------------------------------------------------------------------------

def fetch_propublica(query="community", page=0):
    """
    Fetch nonprofits from ProPublica API.
    Returns (list_of_results, api_ok: bool).
    """
    import urllib.request, urllib.parse

    NTEE_MAP = {
        "A": "Arts & Culture",   "B": "Education",       "C": "Environment",
        "D": "Animal Welfare",   "E": "Healthcare",       "F": "Mental Health",
        "G": "Healthcare",       "H": "Healthcare",       "I": "Crime & Legal",
        "J": "Employment",       "K": "Food & Agriculture","L": "Housing & Shelter",
        "M": "Public Safety",    "N": "Recreation & Sports","O": "Youth Development",
        "P": "Human Services",   "Q": "Civil Rights",     "R": "Civil Rights",
        "S": "Community Development","T": "Philanthropy", "U": "Science & Technology",
        "V": "Public Policy",    "W": "Public Policy",    "X": "Religion",
        "Y": "Human Services",   "Z": "Community Development",
    }
    
    # Build search queries - use multiple searches for better coverage
    search_queries = []
    if query:
        search_queries.append(query)
    else:
        # Default searches for common nonprofit terms in Alabama
        search_queries = ["huntsville", "madison county", "north alabama"]
    
    all_results = []
    api_ok = False
    
    for search_query in search_queries[:2]:  # Limit to 2 queries to avoid slowdown
        params = {"q": search_query, "state[id]": "AL", "page": page}
        url = "https://projects.propublica.org/nonprofits/api/v2/search.json?" + urllib.parse.urlencode(params)

        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "CommunityResourceHub/1.0 (Northern Alabama Resource Directory)",
                "Accept": "application/json"
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status != 200:
                    continue
                body = json.loads(resp.read().decode())
                api_ok = True

            for org in body.get("organizations", []):
                ntee = (org.get("ntee_code") or "")[:1].upper()
                cat = NTEE_MAP.get(ntee, "Community Development")
                city = (org.get("city") or "").title()
                state = org.get("state") or ""
                addr = ", ".join(p for p in [city, state] if p)

                if not is_alabama_location(addr):
                    continue

                ein = str(org.get("ein", ""))
                name = org.get("name", "Unknown")
                
                # Generate better description
                description = generate_ai_description(name, cat, addr)
                
                all_results.append({
                    "name":        name,
                    "category":    cat,
                    "description": description,
                    "address":     addr,
                    "phone":       "",
                    "website":     f"https://projects.propublica.org/nonprofits/organizations/{ein}",
                    "ein":         ein,
                    "source":      "nonprofit",
                })

        except Exception as e:
            print(f"[ProPublica error] {e}")
            continue
    
    return all_results, api_ok


# ---------------------------------------------------------------------------
# Pinned resources — always shown on page 0
# ---------------------------------------------------------------------------

PINNED_RESOURCES = [
    {
        "name": "Huntsville Hospital Health System",
        "category": "Healthcare",
        "description": "Community-owned, not-for-profit hospital system — the largest in North Alabama with 20,000 employees. Home to the state's busiest ER, only Pediatric ER, and one of three Level I Trauma Centers in Alabama.",
        "address": "101 Sivley Rd, Huntsville, AL 35801",
        "phone": "(256) 265-1000",
        "website": "https://www.huntsvillehospital.org",
        "source": "pinned",
    },
    {
        "name": "Huntsville Hospital Foundation",
        "category": "Healthcare",
        "description": "Supports the not-for-profit Huntsville Hospital Health System serving 1.3 million people across the region.",
        "address": "801 Clinton Ave. East, Huntsville, AL 35801",
        "phone": "(256) 265-8077",
        "website": "https://www.huntsvillehospitalfoundation.org",
        "source": "pinned",
    },
    {
        "name": "North Alabama Food Bank",
        "category": "Food & Agriculture",
        "description": "Distributes millions of pounds of food annually to hunger-relief agencies across 35 North Alabama counties.",
        "address": "Huntsville, AL",
        "phone": "(256) 533-1917",
        "website": "https://www.nafb.net",
        "source": "pinned",
    },
    {
        "name": "United Way of Madison County",
        "category": "Human Services",
        "description": "Connects residents with health, education, and financial stability resources across Madison County.",
        "address": "Huntsville, AL",
        "phone": "(256) 536-0745",
        "website": "https://www.unitedwaymadisoncounty.org",
        "source": "pinned",
    },
    {
        "name": "NAMI North Alabama",
        "category": "Mental Health",
        "description": "Mental health education, support groups, and advocacy for individuals and families across North Alabama.",
        "address": "Huntsville, AL",
        "phone": "(256) 489-0888",
        "website": "https://www.naminorthalabama.org",
        "source": "pinned",
    },
    {
        "name": "Boys & Girls Club of North Alabama",
        "category": "Youth Development",
        "description": "After-school and summer programs providing safe, enriching environments for youth across the region.",
        "address": "Huntsville, AL",
        "phone": "(256) 536-4388",
        "website": "https://www.bgcna.org",
        "source": "pinned",
    },
    {
        "name": "Habitat for Humanity - Greater Huntsville",
        "category": "Housing & Shelter",
        "description": "Builds and repairs affordable homes in partnership with families in need across the Huntsville area.",
        "address": "Huntsville, AL",
        "phone": "(256) 539-5154",
        "website": "https://www.habitathuntsville.org",
        "source": "pinned",
    },
    {
        "name": "Legal Services Alabama - Huntsville",
        "category": "Crime & Legal",
        "description": "Free civil legal assistance for low-income residents of Northern Alabama.",
        "address": "Huntsville, AL",
        "phone": "(256) 536-9645",
        "website": "https://www.legalservicesalabama.org",
        "source": "pinned",
    },
    {
        "name": "Merrimack Hall Performing Arts Center",
        "category": "Arts & Culture",
        "description": "Nonprofit arts center offering performances and programs for people with special needs in Huntsville.",
        "address": "Huntsville, AL",
        "phone": "(256) 534-6455",
        "website": "https://www.merrimackhall.com",
        "source": "pinned",
    },
    {
        "name": "Huntsville Animal Services",
        "category": "Animal Welfare",
        "description": "City shelter offering pet adoption, lost & found, and low-cost spay/neuter programs.",
        "address": "Huntsville, AL",
        "phone": "(256) 883-3785",
        "website": "https://www.huntsvilleal.gov/residents/animal-services",
        "source": "pinned",
    },
    {
        "name": "Huntsville Public Library",
        "category": "Education",
        "description": "Free public library system with digital resources, job search help, literacy programs, and community events.",
        "address": "Huntsville, AL",
        "phone": "(256) 532-5940",
        "website": "https://www.hmcpl.org",
        "source": "pinned",
    },
    {
        "name": "Community Action Agency of Huntsville",
        "category": "Community Development",
        "description": "Provides Head Start, energy assistance (LIHEAP), and weatherization programs to low-income families.",
        "address": "Huntsville, AL",
        "phone": "(256) 851-6170",
        "website": "https://www.caah.org",
        "source": "pinned",
    },
]

FALLBACK_RESOURCES = PINNED_RESOURCES  # alias — used when all APIs fail


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    spotlights = read_json(SPOTS_FILE)
    return render_template("index.html", spotlights=spotlights, categories=ALL_CATEGORIES)

@app.route("/learn")
def learn():
    return render_template("learn.html")

@app.route("/references")
def references():
    return render_template("references.html")

@app.route("/contact")
def contact():
    return render_template("contact.html")

@app.route("/admin")
def admin():
    return render_template("admin.html")


@app.route("/api/resources")
def api_resources():
    """GET /api/resources?q=...&category=...&page=0&enrich=1"""
    query    = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    page     = int(request.args.get("page", 0))
    enrich   = request.args.get("enrich", "1") == "1"  # Enable enrichment by default

    def filter_by_query(items, q):
        if not q:
            return items
        ql = q.lower()
        return [
            r for r in items
            if ql in r.get("name", "").lower()
            or ql in r.get("description", "").lower()
            or ql in r.get("category", "").lower()
        ]

    def filter_by_category(items, cat):
        if not cat:
            return items
        cl = cat.lower()
        return [r for r in items if cl in r.get("category", "").lower()]

    # --- Pinned (always on page 0) ---
    pinned = filter_by_category(filter_by_query(PINNED_RESOURCES, query), category) if page == 0 else []

    # --- User submitted ---
    user_resources = filter_by_category(filter_by_query(read_json(USER_FILE), query), category)

    # --- Geoapify local places ---
    geo_results, geo_ok = fetch_geoapify(query=query, category=category, page=page, enrich=enrich)

    # --- ProPublica nonprofits ---
    pp_query = query if query else ""
    pp_results, pp_ok = fetch_propublica(query=pp_query, page=page)
    pp_results = filter_by_category(pp_results, category)

    # Fallback if both APIs failed
    if not geo_ok and not pp_ok and page == 0:
        geo_results = filter_by_category(filter_by_query(FALLBACK_RESOURCES, query), category)

    # --- Merge with deduplication by name ---
    seen = set()
    combined = []
    for r in pinned + user_resources + geo_results + pp_results:
        key = r.get("name", "").lower().strip()
        if key not in seen:
            seen.add(key)
            combined.append(r)

    api_ok = geo_ok or pp_ok
    
    # Save description cache
    save_description_cache()
    
    return jsonify({
        "count":     len(combined),
        "resources": combined,
        "api_ok":    api_ok,
        "source":    "live" if api_ok else "fallback",
        "sources": {
            "geoapify":   geo_ok,
            "propublica": pp_ok,
        },
        "ai_enabled": bool(GROQ_API_KEY),
    })


@app.route("/api/resources/<name>/enrich", methods=["GET"])
def enrich_single_resource(name):
    """
    Enrich a single resource with additional data.
    GET /api/resources/Providence%20Classical%20School/enrich
    """
    address = request.args.get("address", "Huntsville, AL")
    category = request.args.get("category", "Education")
    
    resource = {
        "name": name,
        "address": address,
        "category": category,
        "description": ""
    }
    
    enriched = enrich_resource(resource)
    return jsonify(enriched)


@app.route("/api/resources/submit", methods=["POST"])
def submit_resource():
    data = request.get_json(force=True)
    required = ["name", "category", "description", "contact"]
    for field in required:
        if not data.get(field, "").strip():
            return jsonify({"ok": False, "error": f"'{field}' is required."}), 400
    resource = {
        "name":        data["name"].strip(),
        "category":    data["category"].strip(),
        "description": data["description"].strip(),
        "contact":     data.get("contact", "").strip(),
        "phone":       data.get("contact", "").strip(),
        "address":     data.get("address", "").strip(),
        "website":     data.get("website", "").strip(),
        "source":      "user",
    }
    resources = read_json(USER_FILE)
    resources.append(resource)
    write_json(USER_FILE, resources)
    return jsonify({"ok": True, "resource": resource}), 201


@app.route("/api/spotlights")
def api_spotlights():
    return jsonify(read_json(SPOTS_FILE))

@app.route("/api/categories")
def api_categories():
    return jsonify(ALL_CATEGORIES)

@app.route("/api/contact/submit", methods=["POST"])
def submit_contact():
    from datetime import datetime
    data = request.get_json(force=True)
    required = ["name", "email", "subject", "message"]
    for field in required:
        if not data.get(field, "").strip():
            return jsonify({"ok": False, "error": f"'{field}' is required."}), 400
    message = {
        "name":      data["name"].strip(),
        "email":     data["email"].strip(),
        "subject":   data["subject"].strip(),
        "message":   data["message"].strip(),
        "timestamp": datetime.now().isoformat(),
    }
    messages = read_json(CONTACT_FILE)
    messages.append(message)
    write_json(CONTACT_FILE, messages)
    return jsonify({"ok": True, "message": message}), 201

@app.route("/api/contact/messages")
def get_contact_messages():
    return jsonify({"messages": read_json(CONTACT_FILE)})

@app.route("/api/admin/resources")
def get_admin_resources():
    return jsonify({"resources": read_json(USER_FILE)})

@app.route("/api/status")
def api_status():
    """Check API status and configuration."""
    return jsonify({
        "geoapify_configured": bool(GEOAPIFY_KEY),
        "ai_configured": bool(GROQ_API_KEY),
        "ai_provider": "groq" if GROQ_API_KEY else None,
        "description_cache_size": len(_description_cache),
    })


@app.route("/api/clear-cache", methods=["POST", "GET"])
def api_clear_cache():
    """Clear the description cache to regenerate AI descriptions."""
    cleared = clear_description_cache()
    return jsonify({
        "success": True,
        "cleared": cleared,
        "message": f"Cleared {cleared} cached descriptions. Reload to regenerate with AI."
    })


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    os.makedirs(DATA_DIR, exist_ok=True)
    for f in [USER_FILE, SPOTS_FILE, CONTACT_FILE]:
        if not os.path.exists(f):
            write_json(f, [])

    print("\n  Northern Alabama Community Resource Hub")
    print("  ========================================")
    
    if not GEOAPIFY_KEY:
        print("  ⚠  No Geoapify key — local places search disabled.")
        print("     Get a free key at: https://myprojects.geoapify.com")
    else:
        print("  ✓ Geoapify key loaded.")
    
    if GROQ_API_KEY:
        print("  ✓ Groq API key loaded (AI descriptions enabled).")
    else:
        print("  ⚠  No Groq key — using template descriptions.")
        print("     Get a FREE key at: https://console.groq.com")
    
    print(f"\n  Description cache: {len(_description_cache)} entries")
    print("\n  Open http://localhost:5000 in your browser.\n")
    
    app.run(debug=True, host="0.0.0.0", port=5000, use_reloader=False)




