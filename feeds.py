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
    # ===================== CUBA, THE CARIBBEAN & LATIN AMERICA ============
    # Grouped into a pinned section at the very top of the page. Their names
    # must match REGIONAL_SOURCES (below) exactly.
    ("Rialta",                          "https://rialta.org/feed/",                          "ideas",      "news"),
    ("OnCuba News",                     "https://oncubanews.com/feed/",                      "ideas",      "news"),
    ("Hypermedia Magazine",             "https://www.hypermediamagazine.com/feed/",          "ideas",      "news"),
    ("El Estornudo",                    "https://revistaelestornudo.com/feed/",              "ideas",      "news"),
    ("Repeating Islands",               "https://repeatingislands.com/feed/",                "ideas",      "news"),
    ("80grados",                        "https://www.80grados.net/feed/",                    "ideas",      "news"),
    ("Artburst Miami",                  "https://www.artburstmiami.com/feed/",               "art",        "news"),
    ("Artishock",                       "https://artishockrevista.com/feed/",                "art",        "news"),
    ("Terremoto",                       "https://terremoto.mx/en/feed/",                     "art",        "news"),
    ("Puerto Rico Art News",            "https://www.puertoricoartnews.com/feeds/posts/default?alt=rss", "art", "news"),
    ("Letras Libres",                   "https://letraslibres.com/feed/",                    "literature", "news"),
    ("Latin American Literature Today", "https://latinamericanliteraturetoday.org/feed/",    "literature", "news"),
    ("Remezcla",                        "https://remezcla.com/feed/",                        "music",      "news"),

    # ============================ GASTRONOMY (global + key US cities) =====
    ("Eater",                           "https://www.eater.com/rss/index.xml",               "gastronomy", "news"),
    ("Eater New York",                  "https://ny.eater.com/rss/index.xml",                "gastronomy", "news"),
    ("Eater Miami",                     "https://miami.eater.com/rss/index.xml",             "gastronomy", "news"),
    ("Eater LA",                        "https://la.eater.com/rss/index.xml",                "gastronomy", "news"),
    ("Eater Atlanta",                   "https://atlanta.eater.com/rss/index.xml",           "gastronomy", "news"),
    ("Saveur",                          "https://www.saveur.com/feed/",                      "gastronomy", "news"),
    ("Bon Appétit",                     "https://www.bonappetit.com/feed/rss",               "gastronomy", "news"),
    ("Honest Cooking",                  "https://honestcooking.com/feed/",                   "gastronomy", "news"),

    # ============================ FASHION (global) ========================
    ("Vogue",                           "https://www.vogue.com/feed/rss",                    "fashion",    "news"),
    ("WWD",                             "https://wwd.com/feed/",                             "fashion",    "news"),
    ("Fashionista",                     "https://fashionista.com/.rss/excerpt/",             "fashion",    "news"),
    ("Hypebeast",                       "https://hypebeast.com/feed",                        "fashion",    "news"),
    ("The Cut",                         "https://www.thecut.com/rss/index.xml",              "fashion",    "news"),

    # ============================ PODCASTS ================================
    ("Pop Culture Happy Hour",          "https://feeds.npr.org/510282/podcast.xml",          "podcast",    "news"),
    ("Fresh Air",                       "https://feeds.npr.org/381444908/podcast.xml",       "podcast",    "news"),
    ("Talk Art",                        "https://feeds.acast.com/public/shows/f6a980f6-3f5c-482b-9da0-1b92892998da", "podcast", "news"),
    ("The Great Women Artists",         "https://feeds.soundcloud.com/users/soundcloud:users:698800785/sounds.rss", "podcast", "news"),
    ("99% Invisible",                   "https://feeds.simplecast.com/BqbsxVfO",             "podcast",    "news"),
    ("The Slowdown",                    "https://feeds.publicradio.org/public_feeds/the-slowdown", "podcast", "news"),
    ("The Big Picture",                 "https://feeds.megaphone.fm/the-big-picture",        "podcast",    "news"),
    ("Talk Easy with Sam Fragoso",      "https://rss.art19.com/talk-easy-with-sam-fragoso",  "podcast",    "news"),

    # ============================ THE WIRE (news by medium) ===============
    # --- Film & Television ---
    ("IndieWire",            "https://www.indiewire.com/feed/",        "film", "news"),
    ("Variety",              "https://variety.com/feed/",              "film", "news"),
    ("The Hollywood Reporter","https://www.hollywoodreporter.com/feed/","film", "news"),
    ("Deadline",             "https://deadline.com/feed/",             "film", "news"),
    ("Cineuropa",            "https://cineuropa.org/en/rss/",          "film", "news"),
    ("Screen Daily",         "https://www.screendaily.com/rss",        "film", "news"),
    # --- Animation ---
    ("Cartoon Brew",         "https://www.cartoonbrew.com/feed",       "animation", "news"),
    ("Animation Magazine",   "https://www.animationmagazine.net/feed", "animation", "news"),
    # --- Games & Interactive ---
    ("Polygon",              "https://www.polygon.com/rss/index.xml",  "games", "news"),
    ("Rock Paper Shotgun",   "https://www.rockpapershotgun.com/feed",  "games", "news"),
    ("Eurogamer",            "https://www.eurogamer.net/feed",         "games", "news"),
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
    # --- Comics & Graphic Novels ---
    ("The Comics Journal",   "https://www.tcj.com/feed/",              "comics", "news"),
    ("The Beat",             "https://www.comicsbeat.com/feed/",       "comics", "news"),
    ("Women Write About Comics", "https://womenwriteaboutcomics.com/feed/", "comics", "news"),
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
    ("The Guardian — Books", "https://www.theguardian.com/books/rss",  "literature", "book"),
    ("The New York Times — Books","https://rss.nytimes.com/services/xml/rss/nyt/Books.xml","literature","book"),
    ("Chicago Review of Books","https://chireviewofbooks.com/feed/",    "literature", "book"),
    ("Public Books",         "https://www.publicbooks.org/feed/",      "ideas", "book"),
    ("The Millions",         "https://themillions.com/feed",           "literature", "book"),
]

# THE WIRE: medium sections, in display order.
CATEGORIES = [
    # FILM & SCREEN
    ("film",        "Film &amp; Television"),
    ("animation",   "Animation"),
    ("games",       "Games &amp; Interactive"),
    # THEATER — the stage & sound arts
    ("theater",     "Theater &amp; Stage"),
    ("dance",       "Dance"),
    ("music",       "Music"),
    ("podcast",     "Podcasts"),
    # ART — the visual & made arts
    ("art",         "Visual Art"),
    ("photography", "Photography"),
    ("comics",      "Comics &amp; Graphic Novels"),
    ("design",      "Design &amp; Architecture"),
    ("fashion",     "Fashion &amp; Style"),
    ("gastronomy",  "Gastronomy &amp; Culinary Arts"),
    # LETTERS
    ("literature",  "Literature &amp; Poetry"),
    # IDEAS
    ("ideas",       "Ideas &amp; Humanities"),
]

# THE REVIEW: the three Arts & Letters Daily-style columns, in display order.
COLUMNS = [
    ("note",  "Articles of Note"),
    ("book",  "New Books"),
    ("essay", "Essays &amp; Opinions"),
]

# Sources whose items are gathered into the pinned section at the very top of
# the page ("Cuba, the Caribbean & Latin America"), regardless of art form.
# Names MUST match the Display Name used in FEEDS above, exactly.
REGIONAL_SOURCES = {
    "Rialta", "OnCuba News", "Hypermedia Magazine", "El Estornudo",
    "Repeating Islands", "80grados", "Artburst Miami", "Artishock",
    "Terremoto", "Puerto Rico Art News", "Letras Libres",
    "Latin American Literature Today", "Remezcla",
}
