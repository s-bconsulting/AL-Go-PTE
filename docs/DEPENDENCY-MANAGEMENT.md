# Gestion des dépendances

Comment AL-Go résout les dépendances entre apps AL — à l'intérieur d'un même repo, entre projets d'un même repo, et entre repos séparés (le cas le plus fréquent pour une app de base partagée entre plusieurs clients).

## 1. Dépendances internes à un même repo (`app.json`)

Chaque app AL déclare ses dépendances dans son propre `app.json` :

```json
"dependencies": [
  {
    "id": "<guid>",
    "name": "Base App Name",
    "publisher": "Publisher",
    "version": "1.0.0.0"
  }
]
```

Si un repo contient plusieurs apps (listées dans `appFolders`/`testFolders` de `.AL-Go/settings.json`), **AL-Go calcule automatiquement l'ordre de compilation** à partir de ce graphe de dépendances — inutile de trier `appFolders` toi-même dans le bon ordre.

## 2. Dépendances externes, vers une app publiée depuis un autre repo AL-Go

C'est le mécanisme central quand une app dépend d'une **app publiée depuis un autre repo** — typiquement une app de base/commune partagée entre plusieurs clients. Ça se configure dans `.AL-Go/settings.json` avec `appDependencyProbingPaths` :

```json
"appDependencyProbingPaths": [
  {
    "repo": "https://github.com/s-bconsulting/NomDuRepoDependance",
    "version": "latest",
    "release_status": "release",
    "projects": "*",
    "authTokenSecret": "PAT_SI_REPO_PRIVE"
  }
]
```

### Détail des champs

- **`repo`** : URL complète du repo GitHub qui publie l'app dont on dépend.
- **`version`** : `latest` pour toujours prendre la plus récente correspondant à `release_status`, ou un tag précis pour figer une version.
- **`release_status`** : source des `.app` à récupérer —
  - `release` : la dernière vraie release GitHub (recommandé pour une dépendance stable en production).
  - `prerelease` : releases marquées prerelease incluses.
  - `draft` : même les releases en brouillon.
  - `latestBuild` : dernier artefact de CI/CD **réussi**, même sans release publiée (utile en développement, pour suivre le repo de base au jour le jour).
  - `thisBuild` : cas d'un repo multi-projets — utilise ce qui vient d'être compilé dans le **même run**, voir section 3.
- **`projects`** : `"*"` pour tous les projets du repo source, ou une liste précise si ce repo est lui-même multi-projets.
- **`authTokenSecret`** : nom d'un secret GitHub contenant un PAT (Personal Access Token) avec accès en lecture au repo source. **Obligatoire dès que le repo source est privé** — ce qui est le cas de tous les repos `s-bconsulting`.

AL-Go télécharge alors le `.app` correspondant **avant** la compilation, et l'utilise comme référence de symboles — exactement comme une dépendance normale déclarée dans `app.json`, mais résolue automatiquement à chaque run de CI/CD au lieu d'être un fichier `.app` committé en dur dans le repo consommateur.

## 3. Repo multi-projets (un seul repo, plusieurs apps indépendantes)

Si un seul repo contient plusieurs "projets" AL-Go (chacun avec son propre dossier et son propre `.AL-Go/settings.json`), le fichier au niveau du repo `.github/AL-Go-Settings.json` liste ces `projects`, et AL-Go orchestre leur build dans le bon ordre.

Un projet peut alors dépendre d'un autre **du même repo** via `release_status: "thisBuild"` dans ses `appDependencyProbingPaths` — au lieu d'aller chercher une release existante, il utilise l'app tout juste compilée dans le même run du pipeline.

## 4. Mise à jour des dépendances

Quand le repo de base publie une nouvelle version, le repo consommateur **ne se met pas à jour tout seul automatiquement** :

- Avec `release_status: "release"` (ou `latestBuild`) et `version: "latest"`, le **prochain** CI/CD du repo consommateur récupérera bien la nouvelle version — mais rien ne déclenche ce CI/CD immédiatement après la publication côté repo de base.
- Pour un vrai enchaînement automatique (le repo de base publie → les repos qui en dépendent se reconstruisent et se testent aussitôt), il faut le construire soi-même — par exemple un `repository_dispatch` envoyé depuis le workflow de release du repo de base, capté par un déclencheur dédié dans chaque repo consommateur. Ce n'est **pas** fourni nativement par AL-Go.

## Résumé pratique

| Besoin | Mécanisme |
|---|---|
| Une app dépend d'une autre app du **même dossier de projet** | `dependencies` dans `app.json`, ordre de build automatique |
| Une app dépend d'une app d'un **autre projet du même repo** | `appDependencyProbingPaths` avec `release_status: "thisBuild"` |
| Une app dépend d'une app publiée par un **autre repo** (cas le plus courant : base app commune) | `appDependencyProbingPaths` avec `release_status: "release"` (ou `latestBuild` en dev), `authTokenSecret` obligatoire si le repo source est privé |
| Répercuter automatiquement une nouvelle version de la dépendance | Pas natif — à construire via `repository_dispatch` si nécessaire |
