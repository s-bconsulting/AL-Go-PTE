# Planification des déploiements en production (DeployToSaaS.ps1)

Documentation du hook `.github/DeployToSaaS.ps1`, ajouté le 10/09/2026.

## Pourquoi ce script existe

Business Central Admin Center permet, pour une extension PTE, de planifier son installation plutôt que de l'installer immédiatement : **Immediate**, **Update Window** (dans la prochaine fenêtre de maintenance de l'environnement), **Next Minor Update** ou **Next Major Update** (à la prochaine mise à jour de plateforme).

**AL-Go ne permet pas de choisir ça nativement.** Son mécanisme de déploiement standard (`Deploy.ps1` → `Publish-PerTenantExtensionApps` de BcContainerHelper) passe par l'**ancienne "Automation API"**, qui ne connaît que 3 valeurs : `Current version`, `Next minor version`, `Next major version` — **pas** `Update Window`. Cette option-là vient d'une **API Admin Center plus récente** (`/admin/{apiVersion}/.../apps/pteInstall`, introduite en 2026), que BcContainerHelper n'enveloppe pas encore.

## Comment ça marche

AL-Go a un point d'extension natif dans `Deploy.ps1` : s'il trouve un fichier `.github/DeployTo<EnvironmentType>.ps1`, il l'utilise **à la place** de sa logique interne. `EnvironmentType` vaut toujours `"SaaS"` pour un environnement cloud (ce n'est **pas** "Production"/"Sandbox" — cette distinction n'existe pas dans les settings AL-Go, elle vient de la nature réelle de l'environnement côté BC, déterminée dynamiquement). D'où le nom du fichier : **`.github/DeployToSaaS.ps1`**.

Ce hook s'applique donc à **tous** les environnements cloud (sandbox et production), et gère les deux cas différemment :

- **Sandbox** : comportement inchangé par rapport à AL-Go standard — publication immédiate via l'endpoint de dev (`Publish-BcContainerApp -useDevEndpoint`).
- **Production** : appel direct à la nouvelle Admin Center API (`pteInstall`), qui supporte les 4 valeurs de planification.

## Configuration

Dans `.AL-Go/settings.json`, par environnement (remplacer `<NomEnv>` par le nom exact de l'environnement) :

```json
"DeployTo<NomEnv>": {
  "deploymentSchedule": "UpdateWindow"
}
```

Valeurs possibles : `Immediate` (défaut si absent), `UpdateWindow`, `NextMinorUpdate`, `NextMajorUpdate`.

## ⚠️ Garde-fou important : continuousDeployment

**Incident du 10/09/2026** : la première version de ce script ne reproduisait pas un garde-fou natif d'AL-Go, et a planifié une installation en production à **chaque commit**, via la livraison continue de la CI/CD — alors que `continuousDeployment` était à `false` pour cet environnement (ce qui aurait dû bloquer le déploiement automatique selon la logique standard d'AL-Go).

**Cause** : le garde-fou d'origine (*"si ce n'est pas un environnement sandbox, ET que le déclencheur est la CI/CD automatique, ET que `continuousDeployment` n'est pas explicitement `true` → ne pas déployer"*) ne vit que dans la branche **par défaut** de `Deploy.ps1` — un script `DeployTo<Type>.ps1` personnalisé la court-circuite entièrement et doit la réimplémenter lui-même.

**Le script actuel reproduit ce garde-fou** : un run manuel de `Publish To Environment` (type `Publish`) fonctionne normalement en prod ; un déclenchement automatique par la CI/CD (type `CD`) est **ignoré** (avec un avertissement dans les logs) tant que `continuousDeployment` n'est pas explicitement activé pour cet environnement.

**Si vous modifiez ce script à l'avenir**, ne retirez jamais cette vérification sans en avoir conscience — c'est ce qui empêche un simple commit de déclencher un déploiement en production non désiré.

## Prérequis d'authentification

Le compte/l'application utilisé pour le secret `AUTHCONTEXT` de l'environnement de production doit avoir les **droits Admin Center** (pas seulement les droits "Automation API" habituels, qui suffisaient pour l'ancien mécanisme). Une application d'entreprise (Enterprise Application) avec les droits admin center fonctionne.

## Limite connue

L'API `pteInstall` installe **un seul fichier `.app` par appel** — le script boucle sur `$parameters.Apps` si plusieurs apps PTE doivent être déployées. Les dépendances (`$parameters.Dependencies`) continuent de passer par l'ancienne Automation API (`Publish-PerTenantExtensionApps`), car la planification n'a de sens que pour l'app principale.

## Workflow `Create Release With Deploy` (ajouté le 14/09/2026)

`.github/workflows/CreateReleaseWithDeploy.yaml` — reprend à l'identique tous les jobs du workflow `Create release` généré par AL-Go (création de la release, upload des artefacts, branche de release, incrément de version), et ajoute deux jobs après :

- **`DetermineReleaseDeployEnvironments`** : lit les settings, ne garde que les environnements dont le bloc `DeployTo<NomEnv>` a `"deployAfterRelease": true`.
- **`DeployAfterRelease`** : déploie (via `DeployToSaaS.ps1`, **inchangé** — le filtrage se fait entièrement en amont, pas besoin d'y toucher) uniquement sur ces environnements, avec la version qui vient d'être publiée. Ne se déclenche que si `releaseType == 'Release'` (pas pour une Prerelease ou un Draft).

### Activer le déploiement automatique après une release

```json
"DeployToSB_Consulting": {
  "deploymentSchedule": "UpdateWindow",
  "deployAfterRelease": true
}
```

### Pièges rencontrés en le construisant

- **`ValidateWorkflowInput@v9.2`** (repris de `Create release` par erreur au départ) ne fonctionne que pour les workflows **officiels** d'AL-Go — elle cherche un script `Validate-<nomduworkflow>.ps1` intégré dans `microsoft/AL-Go-Actions` lui-même, sans point d'extension pour un workflow personnalisé (`throw "No validate workflow script found for <nom>."`). **À retirer systématiquement** de tout nouveau workflow custom qui ne fait pas partie du set standard AL-Go — ce n'est pas indispensable (elle ne validait qu'un format de saisie, `updateVersionNumber`, qui reste de toute façon validé plus tard dans le job `UpdateVersionNumber`).
- **`DetermineArtifactsForRelease`** (aussi repris de `Create release`) refuse de créer une release si le commit `main` actuel ne correspond pas exactement au commit du dernier build CI/CD réussi (`"The main branch has changed since the last successful build."`) — comportement standard d'AL-Go, pas un bug introduit par ce workflow. Il faut qu'une CI/CD ait réussi sur le commit exact qu'on veut publier avant de lancer ce workflow (ou activer `useGhTokenWorkflow` pour contourner).
- L'erreur ci-dessus peut être trompeuse si l'échec réel de la CI/CD vient d'ailleurs (ex. un token `AUTHCONTEXT` expiré sur un environnement sandbox) — toujours vérifier le **dernier run CI/CD réussi** (`gh run list --workflow "CI/CD" --status success`) et comparer son `headSha` au commit `main` actuel avant de conclure que c'est un problème de ce workflow.

## Workflow `Auto Release On Merge` (ajouté le 14/09/2026, ⚠️ non testé)

`.github/workflows/AutoReleaseOnMerge.yaml` — déclenche automatiquement une release (et éventuellement son déploiement planifié) dès qu'une PR est mergée, sans action manuelle.

### Fonctionnement

- Se déclenche sur **tout** merge de PR, sur **toutes les branches** — limitation technique de GitHub : le filtre de déclenchement (`on:`) doit être statique dans le YAML, impossible d'y lire `settings.json` avant que le workflow démarre. Le vrai filtrage se fait donc **à l'intérieur** du job, en tout premier, et s'arrête (quelques secondes, négligeable) si les conditions ci-dessous ne sont pas remplies.
- Lit `.AL-Go/settings.json` → `autoReleaseOnMerge` :
  ```json
  "autoReleaseOnMerge": {
    "enabled": false,
    "branches": [ "main" ],
    "workflowType": "ReleaseWithDeploy"
  }
  ```
  - `enabled: false` par défaut — rien ne se passe tant que ce n'est pas mis à `true` explicitement.
  - `branches` : liste des branches de destination à surveiller (un merge vers une autre branche est ignoré).
  - `workflowType` : `"Release"` (déclenche `Create release`) ou `"ReleaseWithDeploy"` (déclenche `Create Release With Deploy`, voir section précédente).
- Déclenche le workflow choisi via `gh workflow run` (API GitHub), pas un appel direct — le run de ce workflow se termine tout de suite, le vrai workflow de release démarre comme un **run séparé** juste après dans l'onglet Actions.
- Dérive automatiquement le tag de release depuis `app.json` (`Major.Minor.0`), via une **heuristique** : premier `app.json` trouvé en excluant les dossiers ressemblant à des apps de test/performance (`.Test`, `.PerformanceTest`). **À ajuster si la structure du dépôt ne correspond pas à cette hypothèse** (ex. plusieurs vraies apps principales, convention de nommage différente).

### ⚠️ Point de vigilance majeur

Une fois `enabled: true`, **chaque merge sur une branche surveillée déclenche une vraie release et potentiellement un vrai déploiement planifié en production**, sans validation humaine supplémentaire — plus radical que tout ce qu'on a construit jusqu'ici. À activer uniquement en connaissance de cause, et à tester d'abord sur un dépôt/branche non-critique avant un usage réel.
