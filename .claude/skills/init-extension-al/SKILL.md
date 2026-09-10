---
name: init-extension-al
description: Utiliser cette compétence chaque fois que l'utilisateur demande d'initialiser, de créer, ou de mettre en place la structure d'une nouvelle extension AL (Business Central / Dynamics NAV), basée sur le template SB Consulting (Template_ALExtension). Se déclenche sur des demandes comme "initialise mon extension", "crée-moi une nouvelle extension AL", "mets en place la structure de mon projet AL", ou toute mention d'un nouveau projet AL/Business Central pour SB Consulting.
---

# Initialisation d'une extension AL (template SB Consulting)

Cette compétence met en place la structure de répertoires standard d'une extension AL, basée sur le modèle du dépôt privé `s-bconsulting/Template_ALExtension`.

## Répertoires à créer

À la racine du projet, créer les répertoires suivants (dans cet ordre, tous vides au départ) :

```
Codeunit/
ControlAddin/
Enum/
EnumExt/
Interface/
Logo/
PagCust/
Page/
PageExt/
Permissions/
Profiles/
Query/
Report/
ReportExt/
TabExt/
Table/
Translations/
XMLPort/
```

## Étapes

1. Demander (si ce n'est pas déjà précisé) le nom du projet / de l'extension et le chemin où l'initialiser.
2. Créer les 18 répertoires listés ci-dessus à la racine du projet.
3. Ajouter un fichier `.gitkeep` vide dans chaque répertoire créé, pour que Git conserve les dossiers vides dans le dépôt.
4. Créer ou compléter le fichier `.gitignore` à la racine du projet (voir section ci-dessous).
5. Confirmer à l'utilisateur la liste des répertoires créés et le contenu ajouté au `.gitignore`.

## Fichier .gitignore

Créer le fichier `.gitignore` à la racine s'il n'existe pas, ou y ajouter les lignes suivantes s'il existe déjà (sans dupliquer une ligne déjà présente) :

```ignore
# Exclusions standard AL Language / Business Central
.alpackages/
.altemplates/
.snapshots/
*.app
rad.json


# Exclusions spécifiques SB Consulting
.vscode/.alcache
.vscode/rad.json
.vscode/settings.json
SB*.app
Profiler/*.alcpuprofile
.claude/
```

**Notes sur ce bloc :**
- La ligne générique `*.app` exclut déjà tous les fichiers `.app`, la ligne `SB*.app` est donc redondante avec elle mais conservée pour rester fidèle à la demande explicite — ne pas la supprimer sans confirmation de l'utilisateur.
- Ne pas exclure `app.json` (fichier de configuration du projet, à versionner).
- Si l'utilisateur indique que certaines de ces exclusions "standard AL Language" ne correspondent pas à son usage réel, les ajuster et mettre à jour cette compétence en conséquence.
- **Cas vécu** : sur un dépôt AL-Go où `launch.json` est délibérément committé (ex. pour y stocker des informations de tenant client), ne PAS ajouter la ligne `launch.json` à l'exclusion sans confirmation explicite de l'utilisateur — signaler le conflit avant d'appliquer.

## Notes

- Cette liste ne reprend que les répertoires du template original qui ne contiennent pas de point dans leur nom (donc pas de fichiers de configuration à la racine comme `app.json`, `.gitignore`, etc.) — uniquement l'arborescence de dossiers.
- Ne pas créer de sous-dossiers ou de fichiers supplémentaires à l'intérieur de ces répertoires sauf demande explicite de l'utilisateur.
- Si l'utilisateur demande d'ajouter d'autres dossiers non listés ici, les ajouter à cette liste après confirmation, pour garder la compétence à jour avec le template.
