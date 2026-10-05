// French labels displayed for internal codes.
export const STATUS_LABELS = {
  new: "Nouveau",
  to_call: "À appeler",
  called_no_answer: "Pas de réponse",
  callback: "À rappeler",
  interested: "Intéressé",
  meeting: "RDV fixé",
  quote_sent: "Devis envoyé",
  won: "Signé 🎉",
  lost: "Perdu",
  not_interested: "Pas intéressé",
};

export const OPPORTUNITY_LABELS = {
  no_website: "Sans site 🔥🔥",
  hot: "Chaud 🔥",
  warm: "Tiède",
  cold: "Froid",
  unknown_website: "Site à chercher",
};

export const SOURCE_LABELS = {
  government_registry: "INSEE",
  openstreetmap: "OSM",
  google_maps: "Google Maps",
  manual: "Saisie manuelle",
};

export const SOURCE_LONG_LABELS = {
  government_registry: "Registre officiel INSEE / Sirene",
  openstreetmap: "OpenStreetMap",
  google_maps: "Google Maps",
  manual: "Saisie manuelle",
};

export const CONFIDENCE_LABELS = {
  high: { label: "✅ Site vérifié", className: "confidence-high" },
  medium: { label: "⚠️ À vérifier", className: "confidence-medium" },
};

export const WEBSITE_ORIGIN_LABELS = {
  openstreetmap: "OpenStreetMap",
  google_maps: "Google Maps",
  domain_guess: "déduit du nom de l'entreprise",
  search_engine: "trouvé via un moteur de recherche",
  duckduckgo: "trouvé via DuckDuckGo",
  bing: "trouvé via Bing",
  google_browser: "trouvé via Google",
  manual: "saisi manuellement",
};

export const SEVERITY_LABELS = { critical: "Critique", major: "Important", minor: "Mineur" };

export const CALL_OUTCOMES = [
  { outcome: "no_answer", label: "📵 Pas de réponse", followUpDays: 2 },
  { outcome: "callback", label: "🔁 À rappeler", followUpDays: 7, askDate: true },
  { outcome: "interested", label: "👍 Intéressé", followUpDays: 3 },
  { outcome: "meeting", label: "📅 RDV fixé", askDate: true },
  { outcome: "not_interested", label: "👎 Pas intéressé", followUpDays: null },
];

export const METRIC_LABELS = {
  final_url: "Adresse finale",
  http_status: "Code HTTP",
  https: "HTTPS",
  certificate_days_remaining: "Certificat SSL (jours restants)",
  generator: "CMS déclaré",
  site_builder: "Constructeur de site",
  jquery_version: "Version de jQuery",
  has_viewport: "Balise viewport (mobile)",
  mobile_overflow_pixels: "Débordement horizontal mobile (px)",
  mobile_font_size: "Taille du texte sur mobile (px)",
  copyright_year: "Année du copyright",
  font_family: "Police principale",
  word_count: "Nombre de mots",
  load_seconds: "Temps de chargement (s)",
  page_weight_megabytes: "Poids de la page (Mo)",
  request_count: "Nombre de requêtes",
  lighthouse: "Scores Lighthouse",
  title: "Titre de la page",
  click_to_call: "Numéro cliquable",
  call_to_action_above_fold: "Appel à l'action visible",
  trackers: "Traceurs détectés",
  cookie_consent: "Bandeau cookies",
  render_error: "Erreur de rendu",
  technologies: "Technologies détectées",
  largest_paint_seconds: "Affichage du contenu principal (LCP, s)",
  layout: "Indices de mise en page",
  design_signals: "Signes de design daté",
  visual_design_score: "Note visuelle IA (/10)",
  visual_assessment: "Avis de l'IA visuelle",
  crawled_pages: "Pages analysées",
  raw_request_refused: "Requête automatique refusée",
  error: "Erreur",
};
