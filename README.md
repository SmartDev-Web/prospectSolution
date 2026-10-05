# 🎯 Prospect Solution

Outil de prospection local et gratuit pour développeur web freelance. Il permet de :

1. **Trouver** les entreprises d'une zone (ville et rayon) dans vos secteurs cibles.
2. **Trouver leur site web**, ou constater qu'elles n'en ont pas.
3. **Auditer** chaque site : sécurité, mobile, vitesse, technologies obsolètes, SEO, conversion, obligations légales, attentes du métier.
4. **Rédiger automatiquement** la fiche commerciale : diagnostic, plan d'amélioration, script d'appel téléphonique et e-mail de suite.
5. **Suivre** la prospection : statuts, notes, journal d'appels, relances du jour, export CSV.

Tout tourne sur votre PC. Aucun abonnement, aucune clé d'API, aucune carte bancaire.

---

## Installation (Windows)

1. Installez **Python 3.11 ou plus récent** depuis https://www.python.org/downloads/ et **cochez « Add python.exe to PATH »**.
2. Double-cliquez sur **`start.bat`**.
   - Le premier lancement crée l'environnement, installe les dépendances et le navigateur Chromium utilisé pour les analyses (quelques minutes).
   - Les lancements suivants démarrent en quelques secondes.
3. L'interface s'ouvre automatiquement sur http://127.0.0.1:8765.

Sous Linux ou macOS, lancez `./start.sh`.

Les données (base SQLite, captures d'écran, profil du navigateur Google Maps) sont stockées dans le dossier `data/`. Pour sauvegarder votre prospection, copiez ce dossier.

---

## Utilisation

### 1. Réglages
Commencez par l'onglet **⚙️ Réglages** : renseignez votre prénom, votre ville, votre téléphone et votre e-mail. Ils sont injectés dans les scripts d'appel et les e-mails.

### 2. Trouver des prospects

| Onglet | Sources | Légalité | Qualité des sites trouvés |
|---|---|---|---|
| **🔎 Open Data** | Registre officiel INSEE / Sirene + OpenStreetMap | ✅ 100 % légal | Les sites sont déduits du nom ou trouvés via DuckDuckGo, puis vérifiés (la page doit mentionner le nom **et** la ville, le code postal ou le téléphone) |
| **🗺️ Google Maps** | Scraping de Google Maps | ⚠️ Contraire aux CGU de Google | Excellente : site, téléphone, note et nombre d'avis |

**Astuce qui rapporte :** dans Open Data, le filtre **« Entreprises créées après le »** cible les entreprises récentes. Elles n'ont souvent ni site ni fiche Google, et c'est le moment où elles achètent.

### 3. Analyser
Cliquez sur **⚡ Analyser** sur une ligne, ou sur **Analyser les prospects non analysés** pour tout traiter en une fois. Chaque analyse :
- télécharge la page d'accueil et vérifie HTTPS et le certificat SSL ;
- ouvre le site dans un vrai navigateur sur ordinateur **et** sur mobile, avec captures d'écran ;
- mesure le temps de chargement, le poids de la page, le débordement sur mobile et la taille du texte ;
- détecte les CMS obsolètes, les constructeurs grand public (Wix, Jimdo, WebSite X5…), Flash, la mise en page en tableaux et un copyright ancien ;
- vérifie la conversion : numéro cliquable, appel à l'action visible, formulaire, plan d'accès, avis clients ;
- contrôle les obligations légales : mentions légales, bandeau cookies en présence de traceurs ;
- vérifie les attentes du métier : réservation en ligne pour un restaurant, prise de rendez-vous pour un coiffeur, demande de devis et certifications pour un industriel, etc. ;
- calcule un **score sur 100** et un niveau d'opportunité : 🔥🔥 sans site, 🔥 chaud, tiède, froid.

### 4. Appeler
L'onglet **📞 À appeler** liste les relances du jour et les meilleurs prospects jamais contactés. Dans la fiche d'un prospect :
- l'onglet **Script d'appel** donne une ouverture, une accroche personnalisée basée sur le problème le plus parlant du site, les questions de découverte du métier, une proposition et les réponses aux objections ;
- les boutons **Pas de réponse / À rappeler / Intéressé / RDV / Pas intéressé** journalisent l'appel, mettent à jour le statut et programment la relance ;
- l'onglet **E-mail** prépare le mail de suite, à copier ou à ouvrir directement dans votre messagerie.

---

## ⚠️ Google Maps : les risques réels

Le scraping n'est **pas indétectable** : l'outil n'essaie pas de passer pour invisible, il essaie de rester raisonnable.

- **Risque technique :** CAPTCHA, puis blocage temporaire de votre adresse IP par Google (de quelques heures à une journée). Pendant ce temps, Google vous demandera aussi des CAPTCHA dans vos recherches normales.
- **Risque juridique :** c'est une violation des conditions d'utilisation de Google. Pour un usage personnel et modéré, le risque concret de poursuites est très faible. Revendre ces données ou en extraire massivement, c'est une autre histoire (droit des producteurs de bases de données).
- **Ce que fait l'outil pour limiter les risques :**
  - navigateur visible par défaut, ce qui permet de résoudre un CAPTCHA à la main (le scraping reprend tout seul ensuite) ;
  - profil de navigateur persistant, qui se comporte comme un visiteur habituel ;
  - pauses aléatoires entre les fiches ;
  - ouverture des fiches par clic dans la liste ;
  - arrêt propre en cas de blocage en mode invisible.
- **Bonnes pratiques :**
  - quelques centaines de fiches par jour au maximum ;
  - ne vous connectez jamais à votre compte Google dans la fenêtre ouverte par l'outil ;
  - si le CAPTCHA revient souvent, arrêtez-vous pour la journée.

Google modifie régulièrement le code de Maps. Tous les sélecteurs sont regroupés en haut de `app/sources/google_maps.py` (dictionnaire `SELECTORS` et script `PLACE_EXTRACTION_SCRIPT`), ce qui rend la correction rapide.

---

## 🤖 IA locale sur la GTX 1060

Sans IA, les fiches sont rédigées par un moteur de règles fiable et instantané. Avec Ollama, le résumé, l'accroche téléphonique et l'e-mail sont réécrits de façon plus naturelle, gratuitement, sur votre propre carte graphique.

1. Installez **Ollama** : https://ollama.com/download
2. Dans **⚙️ Réglages → Intelligence artificielle locale** :
   - **Mode :** « Lancé par l'application sur la carte choisie » ;
   - **Carte graphique dédiée :** choisissez la **GTX 1060 6 Go** dans la liste (détectée via `nvidia-smi`) ;
   - **Modèle :** `qwen2.5:7b-instruct` (environ 4,7 Go, tient dans les 6 Go de la 1060 et écrit correctement en français) ;
   - enregistrez, cliquez **▶️ Démarrer Ollama**, puis **⬇️ Télécharger le modèle**.
3. Le statut affiche la carte réellement utilisée par Ollama. Vérifiez que c'est bien la 1060.

L'application lance son propre serveur Ollama sur le port 11435, avec `CUDA_VISIBLE_DEVICES` pointé sur l'identifiant unique de la 1060. Ce serveur **ne voit que cette carte** : la 1660 Ti reste entièrement disponible pour Windows et vos jeux. Si l'application Ollama classique tourne déjà sur le port 11434, pas de conflit : les modèles téléchargés sont partagés.

> La 1060 est une carte Pascal (architecture de 2016). Elle est supportée par les versions actuelles d'Ollama, mais NVIDIA abandonne progressivement ces cartes dans ses nouvelles versions de CUDA. Si un jour Ollama ne la détecte plus, restez sur la dernière version d'Ollama qui fonctionne ou utilisez un modèle plus petit (`gemma2:2b`) sur le processeur.

---

## 🧪 Audit Lighthouse (optionnel)

Pour ajouter les scores officiels de Google (performance, accessibilité, SEO), installez Node.js puis `npm install -g lighthouse`, et cochez l'option dans les réglages. Chaque analyse prendra environ 20 secondes de plus.

---

## ⚖️ RGPD et prospection

- La prospection **B2B par téléphone** est autorisée : Bloctel et l'obligation de consentement préalable aux appels commerciaux (en vigueur depuis août 2026) visent les consommateurs, pas les professionnels appelés pour leur activité. Respectez simplement tout refus explicite (statut « Pas intéressé »).
- La prospection **B2B par e-mail** est tolérée par la CNIL si le message concerne l'activité professionnelle du destinataire **et** contient un moyen simple de se désinscrire.
- Les données d'un **entrepreneur individuel** (nom, téléphone, e-mail) sont des données personnelles. Supprimez les prospects « Pas intéressé » au bout d'un certain temps et ne gardez que ce qui sert.
- L'outil ignore les établissements que l'INSEE marque comme non diffusibles (ceux qui ont demandé à ne pas être démarchés).

---

## Architecture

```
app/
  main.py               API HTTP + flux d'événements WebSocket
  workflows.py          Orchestration : recherches, découverte des sites, analyses
  prospects.py          Dépôt central : dédoublonnage, fusion, pipeline, export
  sources/              Registre INSEE, OpenStreetMap, Google Maps, découverte de sites
  scanner/              Sondes HTTP/TLS, rendu navigateur, analyseurs, catalogue des problèmes
  reports/              Rédaction par règles, réécriture optionnelle par le LLM local
  llm/                  Détection des GPU, pilotage d'Ollama
web/                    Interface (HTML, CSS, modules JavaScript natifs, carte Leaflet)
tests/                  Tests automatisés (pytest)
```

- **Temps réel :** chaque changement (prospect ajouté, analyse terminée, progression d'une tâche) est poussé à l'interface par WebSocket. Aucun rafraîchissement manuel, aucune interrogation périodique.
- **Dédoublonnage :** une même entreprise trouvée dans le registre, OpenStreetMap et Google Maps est fusionnée (SIRET, domaine, identifiant Google, ou nom similaire à moins de 250 m).

### Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

---

## Limites connues

- **DuckDuckGo** peut bloquer temporairement la recherche de sites après un grand nombre de requêtes. L'outil le détecte, le signale et continue avec la seule déduction du nom de domaine.
- **Faux « sans site » :** une entreprise du registre peut avoir un site que l'outil n'a pas trouvé, notamment quand son nom commercial diffère de son nom légal. Vérifiez rapidement avant d'appeler, et corrigez l'URL dans la fiche : l'analyse se relance en un clic.
- **Temps de chargement :** il est mesuré depuis votre connexion. Sur une fibre, les sites paraîtront plus rapides que sur la 4G de vos prospects.
