"""
feeds.py  —  YOUR SOURCE LIST  (the file you'll edit most)
==========================================================

Each entry is:  ("Display Name", "https://feed-url", "medium", "kind")

  medium  = the art form / subject. One of:
            film theater art dance music photography design literature ideas
            (drives the "Wire" news sections at the bottom)

  kind    = the DEFAULT type of writing this outlet publishes:
            "news"  -> timely news        -> goes to The Wire (by medium)
            "note"  -> long-form feature  -> goes to The Review > Articles of Note
            "book"  -> book review        -> goes to The Review > New Books
            "essay" -> opinion/essay      -> goes to The Review > Essays & Opinions

With an API key the AI re-classifies each *article* (so a book review on a
news site still lands under New Books). Without a key, this default is used.

Dead / moved / paywalled feeds are skipped automatically and reported each
run, so a bad URL can never crash the robot. Add freely.
"""

FEEDS = [
    # ============================ THE WIRE (news by medium) ===============
    # --- Film & Television ---
    ("IndieWire",            "https://www.indiewire.com/feed/",        "film", "news"),
    ("Variety",              "https://variety.com/feed/",              "film", "news"),
    ("The Hollywood Reporter","https://www.hollywoodreporter.com/feed/","film", "news"),
    ("Deadline",             "https://deadline.com/feed/",             "film", "news"),
    ("Cineuropa",            "https://cineuropa.org/en/rss/",          "film", "news"),
    ("Screen Daily",         "https://www.screendaily.com/rss",        "film", "news"),
    # --- Theater & Stage ---
    ("American Theatre",     "https://www.americantheatre.org/feed/",  "theater", "news"),
    ("Playbill",             "https://playbill.com/rss/news",          "theater", "news"),
    ("BroadwayWorld",        "https://www.broadwayworld.com/rss/",     "theater", "news"),
    ("The Stage (UK)",       "https://www.thestage.co.uk/feed",        "theater", "news"),
    # --- Dance ---
    ("Dance Magazine",       "https://www.dancemagazine.com/feed/",    "dance", "news"),
    # --- Music ---
    ("Pitchfork",            "https://pitchfork.com/rss/news/",        "music", "news"),
    ("NPR Music",            "https://feeds.npr.org/1039/rss.xml",     "music", "news"),
    # --- Photography ---
    ("PetaPixel",            "https://petapixel.com/feed/",            "photography", "news"),
    # --- Visual Art (painting, sculpture) ---
    ("ARTnews",              "https://www.artnews.com/feed/",          "art", "news"),
    ("Hyperallergic",        "https://hyperallergic.com/feed/",        "art", "news"),
    ("Artnet News",          "https://news.artnet.com/feed",           "art", "news"),
    ("The Art Newspaper",    "https://www.theartnewspaper.com/rss",    "art", "news"),
    ("Colossal",             "https://www.thisiscolossal.com/feed/",   "art", "news"),
    # --- Design & Architecture ---
    ("Dezeen",               "https://www.dezeen.com/feed/",           "design", "news"),
    ("ArchDaily",            "https://www.archdaily.com/rss/",         "design", "news"),
    # --- Literature & Poetry (news) ---
    ("Literary Hub",         "https://lithub.com/feed/",               "literature", "news"),
    ("Poetry Foundation",    "https://www.poetryfoundation.org/feed",  "literature", "note"),

    # ====================== THE REVIEW (long-form, criticism, ideas) ======
    # --- Articles of Note (deep dives in ideas, science, culture) ---
    ("Aeon",                 "https://aeon.co/feed.rss",               "ideas", "note"),
    ("The Paris Review",     "https://www.theparisreview.org/blog/feed/","literature", "note"),
    ("The Marginalian",      "https://www.themarginalian.org/feed/",   "ideas", "note"),
    # --- Essays & Opinions ---
    ("The Point",            "https://thepointmag.com/feed/",          "ideas", "essay"),
    ("3 Quarks Daily",       "https://3quarksdaily.com/feed",          "ideas", "essay"),
    # --- New Books (reviews & criticism) ---
    ("New York Review of Books","https://feeds.feedburner.com/nybooks","literature", "book"),
    ("Los Angeles Review of Books","https://lareviewofbooks.org/feed/","literature", "book"),
    ("Public Books",         "https://www.publicbooks.org/feed/",      "ideas", "book"),
    ("The Millions",         "https://themillions.com/feed",           "literature", "book"),
]

# THE WIRE: medium sections, in display order.
CATEGORIES = [
    ("film",        "Film &amp; Television"),
    ("theater",     "Theater &amp; Stage"),
    ("dance",       "Dance"),
    ("music",       "Music"), ("podcast",     "Podcasts"),
    ("art",         "Visual Art"),
    ("photography", "Photography"),
    ("design",      "Design &amp; Architecture"),
    ("literature",  "Literature &amp; Poetry"),
    ("ideas",       "Ideas &amp; Humanities"),
]

# THE REVIEW: the three Arts & Letters Daily-style columns, in display order.
COLUMNS = [
    ("note",  "Articles of Note"),
    ("book",  "New Books"),
    ("essay", "Essays &amp; Opinions"),
]
