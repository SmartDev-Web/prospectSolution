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

**69 secteurs ciblables**, regroupés en familles : métiers de bouche, industrie, commerces locaux, tech et communication (agences de communication, agences web, éditeurs de logiciels, ESN, startups, graphistes, événementiel, imprimeries), bâtiment et artisans, santé et bien-être, professions libérales et conseil, automobile, tourisme et loisirs, services. Chaque famille a ses propres questions de découverte, recommandations et attentes métier (galerie de réalisations pour un artisan, études de cas pour une agence, prise de rendez-vous pour un cabinet médical…). Dans les formulaires de recherche, un champ filtre la liste et une case coche toute une famille.

**Doublons fusionnés automatiquement** après chaque recherche (désactivable dans les réglages). Deux fiches sont considérées identiques si elles partagent le SIREN (plusieurs établissements d'une même entreprise deviennent une seule fiche), l'identifiant Google Maps, le site web, le téléphone avec un nom proche, ou un nom très proche à la même adresse. La fusion garde la fiche la plus ancienne et y rapatrie coordonnées, sources, notes, statut, appels et analyses. Le bouton **🔗 Fusionner les doublons** relance la détection, et cocher plusieurs lignes fait apparaître **🔗 Fusionner la sélection** pour regrouper des fiches à la main.

**Une chaîne passe entre les mailles ?** Dans sa fiche, le bouton **🏬 C'est une chaîne** demande le nom de l'enseigne (Kiabi par exemple), supprime tous les prospects qui la portent et l'ajoute à la liste des enseignes exclues des prochaines recherches. Cette liste se modifie aussi dans **⚙️ Réglages → Chaînes et franchises**.

**Chaînes et franchises exclues** (McDonald's, Subway, Burger King, Leclerc, Brico Marché, Leroy Merlin…) : leur site est géré par le siège national, inutile de les appeler. La détection combine une liste d'environ 390 enseignes, 70 sites nationaux (subwayfrance.fr…), la marque déclarée dans OpenStreetMap et le nombre d'établissements de l'entreprise. Le bouton **🧹 Retirer les chaînes** nettoie une base existante.

#### Comment l'outil trouve les sites web
1. **Déduction du nom de domaine** : variantes du nom et de la ville × extensions `.fr`, `.com`, `.eu`, `.net`, `.org`, `.info`, toutes testées en parallèle.
2. **Moteurs de recherche** (dans Réglages) : DuckDuckGo, Bing, et Google via un vrai navigateur en option (le plus pertinent, mais CAPTCHA possible). Un moteur qui bloque est mis de côté jusqu'à la fin de la tâche.
3. **Vérification par preuves** de chaque site candidat, homepage puis pages contact et mentions légales : nom dans le domaine ou le titre, code postal, ville, rue, téléphone, **SIREN dans les mentions légales**. Une adresse dans un autre département écarte le site (homonymes).
4. **Niveau de confiance** affiché dans la fiche : ✅ *vérifié* (identifiant ou adresse exacte) ou ⚠️ *à vérifier*, avec les preuves. Le bouton **❌ Ce n'est pas le bon site** écarte définitivement ce domaine pour ce prospect.

#### Compléter les fiches avec Google Maps
Les entreprises du registre officiel n'ont presque jamais de téléphone. Le bouton **📞 Compléter les téléphones** (ou **🗺️ Compléter via Google Maps** dans une fiche) cherche « nom + ville » sur Google Maps et récupère le téléphone, le site, la note et les avis. Le site affiché sur la fiche Google remplace une déduction incertaine, et une fiche Google sans site confirme que l'entreprise n'en a pas. Les volumes restent faibles (30 par passage), avec les mêmes précautions que l'onglet Google Maps.

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

L'analyse va plus loin qu'une simple page d'accueil :
- elle attend que les styles et les polices soient chargés avant de mesurer, et écarte les rendus ratés (page vide, erreur, protection anti-robot) au lieu de les noter ;
- elle **explore les pages internes utiles** (contact, mentions légales, carte, tarifs, réservation, devis) pour ne pas reprocher l'absence d'un élément présent ailleurs sur le site ;
- elle mesure l'**affichage du contenu principal (LCP)** plutôt que la fin du chargement de tous les scripts tiers ;
- elle identifie la **technologie** (WordPress et sa vraie version, Elementor, Wix, WebSite X5, Next.js, Bootstrap…) ;
- elle juge l'**âge du design** à partir d'indices (police par défaut, absence de mise en page moderne, constructeur bas de gamme, copyright ancien, techniques des années 2000), ou par l'**IA visuelle** si elle est activée ;
- elle relève les **points forts** (site rapide, à jour, réservation en ligne, bonne réputation Google…) pour commencer l'appel par un compliment sincère.

**Notation :** le score est la somme de 7 catégories pondérées (sécurité 15, mobile 20, vitesse 15, design 20, conversion 20, référencement 7, légal 3). Chaque catégorie a un plancher : dix détails de référencement ne peuvent pas couler un site moderne. Un problème critique (pas de HTTPS, site non mobile, design très daté…) plafonne le score à 40. Une catégorie non mesurable (page impossible à afficher) est exclue du calcul au lieu de compter comme parfaite. Moins de 50 : 🔥 chaud, moins de 70 : tiède, au-delà : froid.

### Corriger un diagnostic
L'analyse peut se tromper. Dans l'onglet **Diagnostic** d'une fiche :
- **✖ Retirer** un point erroné : le score, l'opportunité, l'offre, le script d'appel et l'e-mail sont recalculés sans lui ;
- **➕ Ajouter un point** que vous avez constaté vous-même (titre, explication, gravité, catégorie) ;
- **✏️ Modifier le résumé** depuis l'onglet Synthèse ;
- **↩ Rétablir** un point retiré.

Ces corrections sont conservées lors des analyses suivantes. Un site qui refuse les requêtes automatiques (protection de l'hébergeur renvoyant une erreur 503 ou 403) est désormais ouvert dans un vrai navigateur avant d'être déclaré inaccessible.

### Analyser tous les prospects
Le bouton **🔄 Analyser tous les prospects** relance tout en une tâche : recherche des sites manquants, réanalyse de toutes les fiches (nouveaux contacts, site refait, score à jour), puis fusion des doublons révélés (même téléphone ou même site trouvés entre-temps).

### La liste des prospects
Cliquez sur un en-tête de colonne (score, entreprise, ville, effectif, téléphone, site, opportunité, statut, relance) pour trier, et cliquez à nouveau pour inverser l'ordre. L'effectif provient du registre officiel.

**Filtrer autour d'un lieu :** tapez une ville ou une adresse dans le champ « 📍 Autour de… », choisissez une suggestion et réglez le **Rayon** (5 km par défaut). Seuls les prospects situés dans ce rayon restent affichés, avec une colonne **Distance** triée du plus proche au plus loin. Les fiches sans coordonnées GPS sont conservées si leur ville correspond, et rangées en fin de liste. La croix ✕ retire le filtre. L'export CSV respecte le filtre et ajoute la distance.

### La fiche prospect
Dans **⚙️ Réglages → Fiche client**, cochez ce qui doit s'afficher : effectif recensé, coordonnées (téléphone, adresse, e-mail, site web), synthèse, diagnostic, script d'appel, e-mail, technique, historique.

- **Barre d'actions** : appeler, copier le numéro, rechercher sur Google, Google Maps, ouvrir le site, fiche officielle, compléter via Google Maps.
- **Origine** : « Fiche créée depuis OpenStreetMap / Google Maps / registre INSEE », et les sources qui l'ont complétée.
- **Site** : niveau de confiance, preuves, correction manuelle, rejet, relance de la recherche.
- **Dirigeant** (registre officiel) : le script d'appel propose de le demander par son nom.
- **Synthèse** : offre à proposer (création, refonte, modernisation, optimisation), 3 meilleurs arguments téléphoniques, score par catégorie, points forts, captures ordinateur et mobile.

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

La liste propose **Choix automatique** (Ollama répartit le modèle sur toutes les cartes listées entre parenthèses), puis **Carte 1**, **Carte 2**… pour forcer une carte précise.

**La 1060 n'apparaît pas dans la liste ?** C'est que le pilote NVIDIA ne la voit pas : ouvrez une invite de commandes et tapez `nvidia-smi -L`. Si une seule carte s'affiche, aucun logiciel ne pourra utiliser la 1060 pour le calcul. La page Réglages affiche alors un avertissement avec la cause détectée par Windows :
- **code 22** : carte désactivée dans le Gestionnaire de périphériques → clic droit, « Activer » ;
- **code 43 / 10** : pilote planté ou carte mal alimentée → réinstallation propre du pilote (DDU), câbles PCIe et riser à vérifier ;
- **code 12** : ressources insuffisantes → activer « Above 4G decoding » dans le BIOS ;
- **aucun code** : la carte est vue par Windows mais ignorée par le pilote → réinstaller le pilote NVIDIA complet (il gère les deux cartes, pas besoin d'en installer deux).

L'application lance son propre serveur Ollama sur le port 11435, avec `CUDA_VISIBLE_DEVICES` pointé sur l'identifiant unique de la 1060. Ce serveur **ne voit que cette carte** : la 1660 Ti reste entièrement disponible pour Windows et vos jeux. Si l'application Ollama classique tourne déjà sur le port 11434, pas de conflit : les modèles téléchargés sont partagés.

**IA visuelle (recommandée) :** renseignez un **modèle de vision** (`qwen2.5vl:3b` tient dans les 6 Go de la 1060) puis cliquez à nouveau sur **⬇️ Télécharger le modèle**. Chaque capture d'écran est alors notée de 1 à 10 sur la modernité du design, avec une phrase qui cite les éléments datés. C'est la seule façon fiable de juger un « look » daté : les indices techniques ne voient pas un logo en WordArt.

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

- **Moteurs de recherche** : ils peuvent bloquer temporairement après un grand nombre de requêtes. Bing renvoie même parfois des résultats sans rapport pour piéger les robots : la vérification par preuves les écarte. L'outil met de côté tout moteur qui bloque et continue avec les autres.
- **Faux « sans site » :** une entreprise du registre peut avoir un site que l'outil n'a pas trouvé, notamment quand son nom commercial diffère de son nom légal. Vérifiez rapidement avant d'appeler, et corrigez l'URL dans la fiche : l'analyse se relance en un clic.
- **Temps de chargement :** il est mesuré depuis votre connexion. Sur une fibre, les sites paraîtront plus rapides que sur la 4G de vos prospects.
