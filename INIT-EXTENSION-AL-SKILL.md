# Utiliser la compétence Claude "init-extension-al"

`init-extension-al` est une compétence Claude Code personnelle (pas un fichier de ce template) qui initialise la structure de dossiers standard d'une nouvelle extension AL, sur le modèle du dépôt `s-bconsulting/Template_ALExtension`. Elle se déclenche sur des demandes comme "initialise mon extension", "crée-moi une nouvelle extension AL" ou "mets en place la structure de mon projet AL".

## Ce qu'elle fait

1. Crée 18 dossiers vides à la racine du projet ciblé : `Codeunit/`, `ControlAddin/`, `Enum/`, `EnumExt/`, `Interface/`, `Logo/`, `PagCust/`, `Page/`, `PageExt/`, `Permissions/`, `Profiles/`, `Query/`, `Report/`, `ReportExt/`, `TabExt/`, `Table/`, `Translations/`, `XMLPort/`, chacun avec un `.gitkeep`.
2. Crée ou complète un `.gitignore` avec les exclusions standard AL Language / Business Central et les exclusions spécifiques SB Consulting.

## À faire différemment dans un repo AL-Go

AL-Go exige que chaque app vive dans son **propre sous-dossier** (déclaré dans `appFolders` de `.AL-Go/settings.json`), jamais à la racine du repo. La compétence, elle, crée sa structure à la racine du dossier depuis lequel elle est invoquée - donc dans un repo scaffoldé par ce template :

- **Ne l'invoquez pas à la racine du repo.** Créez d'abord le sous-dossier de l'app (ex. `MonExtension/`), placez-vous dedans, puis invoquez la compétence depuis là - elle y créera les 18 dossiers au bon niveau.
- **N'ajoutez pas son bloc `.gitignore` tel quel.** Ce template scaffolde déjà un `.gitignore` complet à la racine du repo, qui couvre les mêmes exclusions AL/BC. Vérifiez plutôt qu'aucune entrée utile ne manque à ce `.gitignore` racine, sans le dupliquer sous-dossier par sous-dossier - voir [DEPLOYMENT-SCHEDULING.md](DEPLOYMENT-SCHEDULING.md) pour la liste des entrées attendues.
- **Retirez la ligne `launch.json`** si elle apparaît dans le `.gitignore` généré : cette entrée ignore n'importe quel fichier `launch.json`, y compris `.vscode/launch.json`. La convention de ce repo garde volontairement `.vscode/launch.json` suivi par git, car il contient les configurations de debug/publish partagées utiles à l'équipe (seuls `.vscode/rad.json` et `.vscode/settings.json` sont ignorés). Ignorer `launch.json` par erreur revient à perdre ces configurations pour toute l'équipe, silencieusement.
- **N'oubliez pas d'ajouter** le nom du sous-dossier créé à `appFolders` dans `.AL-Go/settings.json`, et de configurer les autres champs requis (`country`, `versioningStrategy`, `versionBCPreserve`/`versionBCMarker`...) - voir [VERSIONING.md](VERSIONING.md).
