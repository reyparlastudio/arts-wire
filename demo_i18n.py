# -*- coding: utf-8 -*-
"""
demo_i18n.py — sample translations used ONLY by --demo, so you can see real
translated pages without an API key. In live use, translate.py + Claude
produces these for ANY language automatically.
  - Spanish ('es'): a complete translated edition (chrome + all items).
  - Arabic  ('ar'): translated chrome with right-to-left layout; item bodies
    stay English with a banner, to demonstrate RTL without hand-faking copy.
"""

DEMO_I18N = {
    "es": {
        "chrome": {
            "kicker": "Cine &middot; Teatro &middot; Arte &middot; Letras &middot; Ideas &middot; En todo el mundo",
            "pieces": "piezas",
            "review_label": "La Reseña &mdash; lecturas largas, libros e ideas",
            "wire_label": "El Cable &mdash; noticias de hoy, por disciplina",
            "subscribe": "Suscríbete &middot; 1 $/mes",
            "art_label": "Una cosa bella",
            "foot1": ("Compilado automáticamente por The Arts Wire. Cada título enlaza con su "
                      "editor original; los resúmenes se redactan de nuevo y remiten a la pieza completa."),
            "foot2": "hecho con cuidado, en piloto automático.",
            "empty": "Nada hoy.",
        },
        "columns": {"note": "Artículos destacados", "book": "Libros nuevos",
                    "essay": "Ensayos y opiniones"},
        "categories": {"film": "Cine y televisión", "theater": "Teatro y escena",
                       "dance": "Danza", "music": "Música", "art": "Arte visual",
                       "photography": "Fotografía", "design": "Diseño y arquitectura",
                       "literature": "Literatura y poesía", "ideas": "Ideas y humanidades"},
        "items": {
            "Does Chalmers's 'Hard Problem' of Consciousness Still Hold Up?": {
                "title": "¿Sigue en pie el «problema difícil» de la conciencia de Chalmers?",
                "summary": "Un análisis amplio sobre si la experiencia subjetiva sigue siendo un enigma genuino o una confusión de categorías.",
                "tags": ["conciencia", "filosofía"]},
            "The Quiet Revolution in How We Write Narrative History": {
                "title": "La revolución silenciosa en cómo escribimos la historia narrativa",
                "summary": "Sobre una generación de historiadores que cambia la gran teoría por la textura, la escena y la vida de la gente común.",
                "tags": ["historia", "oficio"]},
            "James Schuyler, Reconsidered": {
                "title": "James Schuyler, reconsiderado",
                "summary": "Una nueva edición reunida invita a revalorar la atención luminosa y espontánea del poeta de la Escuela de Nueva York.",
                "tags": ["poesía", "retrospectiva"]},
            "A Major Biography Reframes a Forgotten Modernist": {
                "title": "Una biografía importante replantea a un modernista olvidado",
                "summary": "La crítica sostiene que la obra tardía del pintor se ha malinterpretado durante medio siglo.",
                "tags": ["biografía", "modernismo"]},
            "Before Lithium: A Strange History of Treating Mania": {
                "title": "Antes del litio: una extraña historia del tratamiento de la manía",
                "summary": "Cómo la psiquiatría llegó a tientas a un tratamiento que aún no comprende del todo.",
                "tags": ["medicina", "historia"]},
            "The Trouble With Teaching 'AI Literacy' on Campus": {
                "title": "El problema de enseñar «alfabetización en IA» en la universidad",
                "summary": "Un argumento de que las universidades confunden el adiestramiento en herramientas con el trabajo más profundo del juicio.",
                "tags": ["educación", "ia"]},
            "Cannes Unveils a Competition Heavy on First-Time Directors": {
                "title": "Cannes presenta una competición cargada de directores debutantes",
                "summary": "Once cineastas debutantes competirán por la Palma de Oro, la mayor cifra del festival en una década.",
                "tags": ["festival", "cannes"]},
            "National Theatre Names a New Artistic Director": {
                "title": "El National Theatre nombra a un nuevo director artístico",
                "summary": "La institución londinense designa a un director conocido por sus reposiciones a gran escala.",
                "tags": ["dirección", "reino unido"]},
            "A Landmark Restaging Revives a Forgotten Ballet": {
                "title": "Una reposición histórica revive un ballet olvidado",
                "summary": "Reconstruida a partir de la notación y de filmaciones antiguas, la obra vuelve a escena tras ochenta años.",
                "tags": ["ballet", "reposición"]},
            "A Quietly Radical Album Reshapes a Veteran's Sound": {
                "title": "Un álbum discretamente radical redefine el sonido de un veterano",
                "summary": "El disco cambia el pulido de estadio por algo más crudo e inquieto.",
                "tags": ["álbum", "reseña"]},
            "Record Auction Night Signals Renewed Collector Confidence": {
                "title": "Una noche de subasta récord señala una renovada confianza de los coleccionistas",
                "summary": "Una sólida subasta vespertina sugiere que la gama alta del mercado se estabiliza.",
                "tags": ["mercado", "subasta"]},
            "A Striking New Museum Opens on a Reclaimed Waterfront": {
                "title": "Un nuevo y llamativo museo abre en un frente marítimo recuperado",
                "summary": "Los arquitectos convirtieron un muelle en ruinas en una sala luminosa para arte contemporáneo.",
                "tags": ["arquitectura", "museo"]},
        },
    },
    "ar": {
        "chrome": {
            "kicker": "سينما &middot; مسرح &middot; فن &middot; آداب &middot; أفكار &middot; حول العالم",
            "pieces": "مقالات",
            "review_label": "المراجعة &mdash; قراءات طويلة، كتب وأفكار",
            "wire_label": "البرق &mdash; أخبار اليوم، حسب المجال",
            "subscribe": "اشترك &middot; دولار واحد شهريًا",
            "art_label": "شيء جميل واحد",
            "foot1": "يُجمَّع تلقائيًا بواسطة The Arts Wire. كل عنوان يحيل إلى ناشره الأصلي، والملخصات مكتوبة من جديد وتحيل إلى المقال الكامل.",
            "foot2": "صُنع بعناية، ويعمل تلقائيًا.",
            "empty": "لا جديد اليوم.",
            "banner": "يُترجَم نص المقالات تلقائيًا عند تفعيل مفتاح الذكاء الاصطناعي؛ تظهر هنا الواجهة مترجمة كمعاينة لاتجاه الكتابة من اليمين إلى اليسار.",
        },
        "columns": {"note": "مقالات مختارة", "book": "كتب جديدة", "essay": "مقالات ورأي"},
        "categories": {"film": "سينما وتلفزيون", "theater": "مسرح", "dance": "رقص",
                       "music": "موسيقى", "art": "فن بصري", "photography": "تصوير",
                       "design": "تصميم وعمارة", "literature": "أدب وشعر",
                       "ideas": "أفكار وعلوم إنسانية"},
        "items": {},   # bodies stay English; banner explains. RTL layout still applies.
    },
}
