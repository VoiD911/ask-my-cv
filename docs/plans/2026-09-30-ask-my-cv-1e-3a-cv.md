# « Interroge mon CV » — plan 1e-3a : page CV (téléchargement et contact)

> Flux `xops-pipeline`. Règle de périmètre : deux passages de revue au plus ; au-delà, seuls les constats Critique bloquent.

**Goal:** un recruteur trouve en un clic le CV (FR/EN) à télécharger et un moyen de contact.

**Décisions (utilisateur, 2026-09-30) :**
- PDF **généré au build** depuis `data/cv.md` (même source que l'assistant), en français et en anglais ; la traduction anglaise est relue par l'utilisateur avant publication.
- Contact : `job@stevelang.net` et LinkedIn `https://www.linkedin.com/in/steve-cl-lang/`.

## Tâche 1 : page `/cv` et `/en/cv` + PDF
- Page lisible (le CV en HTML, sections du fichier), bouton « Télécharger le PDF », liens de contact.
- PDF produit au build (Playwright/Chromium déjà présent en CI) à partir d'une page d'impression dédiée ; nom de fichier `Steve-Lang-CV-fr.pdf` / `-en.pdf` ; métadonnées (titre, auteur) ; aucune donnée privée (ni adresse, ni téléphone).
- Source anglaise `data/cv.en.md` (traduction fidèle, relue par l'utilisateur) ; un test vérifie que les deux fichiers ont les mêmes sections.
- Lien « CV » dans la navigation ; contact aussi sur l'accueil.
- **Fin :** pages en ligne FR/EN, PDF téléchargeables, axe et Lighthouse verts, CSP inchangée.

## Plus tard (1e-3b, à décider)
- `/demos`, `/projets` (spec §6).
