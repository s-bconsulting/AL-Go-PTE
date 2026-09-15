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

`.github/workflows/AutoReleaseOnMerge.yaml` — déclenche automatiquement une release (et éventuellement son déploiement planifié) dès qu'une PR est mergée dans une branche surveillée, sans action manuelle.

### ⚠️ Pourquoi il attend la CI/CD avant de déclencher, sans pour autant réagir à "n'importe quelle CI/CD"

Le déclencheur reste volontairement `pull_request: types: [closed]` (un vrai merge de PR, sur une branche choisie) — **pas** `workflow_run` sur la réussite de la CI/CD en général. Réagir à n'importe quel run CI/CD réussi aurait aussi déclenché des releases sur le **run planifié nocturne** (`schedule`/cron, que `CI/CD.yaml` d'AL-Go inclut généralement) ou un `workflow_dispatch` manuel, sans qu'aucun merge n'ait eu lieu — bien plus large que ce qu'on veut.

Le problème restait cependant réel : réagir *immédiatement* au merge tirait quasi systématiquement **avant** la fin du run CI/CD que ce même merge déclenche de façon asynchrone (via le push sur la branche), et `DetermineArtifactsForRelease` (dans `CreateRelease`/`CreateReleaseWithDeploy`) refusait alors la release avec `"The main branch has changed since the last successful build."` — pas un vrai garde-fou, juste un échec de timing.

**La version actuelle résout ça sans changer le déclencheur** : une fois le merge confirmé éligible (`enabled` + branche surveillée), le job **attend** (poll toutes les 30s, jusqu'à 90 minutes) qu'un run `CI/CD` correspondant **exactement** au commit de merge (`merge_commit_sha`) se termine, puis vérifie que sa conclusion est `success` avant de déclencher la release. Si la CI/CD échoue ou n'a pas terminé dans le délai, le workflow s'arrête en erreur et **aucune release n'est créée**.

Contrepartie : le job reste actif (sur un runner GitHub hébergé `windows-latest`) pendant toute cette attente, ce qui consomme des minutes facturées le temps que la CI/CD tourne. À surveiller si `autoReleaseOnMerge` est activé sur un repo où la CI/CD est longue ou fréquente ; faire tourner ce job sur le runner self-hosted serait une option si le coût devient significatif.

### Recommandation complémentaire : protection de branche

Ce workflow garantit qu'*une release ne parte pas* sans CI/CD verte sur le commit mergé, mais n'empêche pas en soi un merge non validé (rien n'oblige la CI/CD à être verte pour que le bouton "Merge" soit cliquable). Pour un vrai garde-fou en amont (comme configuré sur `SBLawyer-AL` → branche `master` : 1 review obligatoire, push direct restreint, force-push/suppression bloqués), il est recommandé d'activer sur la branche surveillée par `autoReleaseOnMerge` :

- **Required status checks** = le workflow `CI/CD` (empêche le clic "Merge" tant qu'il n'est pas vert).
- **Required pull request reviews** (au moins 1 approbation).
- **Restrict who can push** (empêche un push direct qui contournerait la revue).

Au 14/09/2026, aucun des repos `ALGOPTESample`, `AL-Go-PTE` ni `AL-Go-AppSource` n'a de protection sur `main` — c'est un réglage GitHub par dépôt (Settings → Branches), pas quelque chose qu'un template ou ce workflow peut propager automatiquement.

### Fonctionnement

- Lit `.AL-Go/settings.json` → `autoReleaseOnMerge` :
  ```json
  "autoReleaseOnMerge": {
    "enabled": false,
    "branches": [ "main" ],
    "workflowType": "ReleaseWithDeploy",
    "versionIncrement": "+0.0.1"
  }
  ```
  - `enabled: false` par défaut — rien ne se passe tant que ce n'est pas mis à `true` explicitement.
  - `branches` : liste des branches de destination à surveiller (un merge vers une autre branche est ignoré).
  - `workflowType` : `"Release"` (déclenche `Create release`) ou `"ReleaseWithDeploy"` (déclenche `Create Release With Deploy`, voir section précédente).
  - `versionIncrement` : valeur passée à `IncrementVersionNumber` sur la branche de développement après la release (voir section suivante) — défaut `"+0.0.1"` si absent.
- Déclenche le workflow choisi via `gh workflow run` (API GitHub), pas un appel direct — le run de ce workflow se termine tout de suite, le vrai workflow de release démarre comme un **run séparé** juste après dans l'onglet Actions.
- Dérive le tag de release depuis `app.json`, **verbatim, les 4 segments tels quels** (ex. `10.4.3.280`) — pas de recomposition en 3 segments. Heuristique de recherche : premier `app.json` trouvé en excluant les dossiers ressemblant à des apps de test/performance (`.Test`, `.PerformanceTest`). **À ajuster si la structure du dépôt ne correspond pas à cette hypothèse** (ex. plusieurs vraies apps principales, convention de nommage différente).
- Si un tag portant cette version existe déjà (le merge n'a pas fait bouger `app.json`), le workflow s'arrête sans rien faire plutôt que d'échouer sur un tag dupliqué.

### Convention de version chez SB Consulting

Contrairement à un simple compteur de build, chez SB Consulting chaque segment de `app.json.version` porte un sens précis, décidé manuellement — ni AL-Go, ni ce workflow ne doivent le recalculer automatiquement :

| Segment | Rôle |
|---|---|
| 1 (Majeur) | Version majeure du produit SB Consulting lui-même (indépendante du cycle de Microsoft — un produit plus récent que BC n'a pas à démarrer à une version aussi haute que BC). |
| 2 (CU) | Cumulative Update du produit. |
| 3 (Mineur/Fix) | Fait aussi office de compteur de build — chaque correctif publié l'incrémente. |
| 4 (marqueur BC) | **Pas un numéro de build** — fixé manuellement, encode la version de Business Central visée (ex. `280` = BC 28 CU 0). Ne change que lors d'un portage vers une nouvelle version de BC, jamais à chaque release. |

Conséquence directe : `app.json.version` doit être bumpé **par la PR elle-même** (politique d'équipe) avant un merge qui doit déclencher une release — `AutoReleaseOnMerge` ne le fait jamais à la place de vous. C'est déjà la convention manuelle utilisée sur `SBLawyer-AL` (où `app.json` sur `main` correspond toujours exactement au tag de la dernière release) ; ce workflow ne fait que l'automatiser une fois la convention respectée en amont.

**⚠️ Non vérifié en pratique** : le tag est transmis tel quel à l'API GitHub de création de release (`createRelease`, aucun parsing semver à cette étape), donc un tag à 4 segments devrait fonctionner sans souci — mais si `CreateReleaseNotes` (génération du changelog) compare des tags entre eux, un comportement avec des tags à 4 segments n'a pas encore été observé en conditions réelles. À surveiller au premier run.

### Incrément de version après la release — sur la branche de développement, jamais sur `main`

`main` reste volontairement figé à la version qui vient d'être publiée — c'est ce qui permet à `app.json` et au tag de release de rester identiques (voir tableau ci-dessus). Mais l'équipe veut quand même que la prochaine version cible soit déjà en place pour la suite du développement, **sans y toucher sur `main`**.

Le workflow bascule donc l'incrément de version sur la branche **source** de la PR qui vient d'être mergée (`github.event.pull_request.head.ref`) — la branche de développement persistante (ex. `develop`), sur laquelle les développeurs continuent de merger leurs propres branches avant qu'elle ne soit à son tour mergée dans `main` pour déclencher une release.

- Valeur appliquée : `autoReleaseOnMerge.versionIncrement` (défaut `"+0.0.1"` si absent) — avance uniquement le 3ᵉ segment (Mineur/Fix), laisse Majeur/CU/marqueur BC intacts. Passé tel quel à l'action `IncrementVersionNumber` du workflow `IncrementVersionNumber.yaml` (inchangé, standard AL-Go), déclenché avec `--ref` sur cette branche.
- **Ne bloque jamais la release** : les deux déclenchements (`Create release`/`Create Release With Deploy`, puis `IncrementVersionNumber`) sont deux runs Actions indépendants — un souci sur le second n'affecte pas le premier.
- **Garde-fou** : si la branche de développement n'existe plus (cas exceptionnel — elle est censée être persistante, jamais supprimée après un merge), le workflow log un avertissement (`::warning::`) et n'essaie pas de déclencher `IncrementVersionNumber` sur une branche inexistante ; l'incrément est alors à faire manuellement.
- L'incrément se fait en `directCommit: true` (commit direct sur la branche de développement, pas de PR à valider en plus) — à changer directement dans le workflow si vous préférez une PR ici aussi.
- **`versioningStrategy: 3` est obligatoire** (ajouté dans `.AL-Go/settings.json`) — confirmé en lisant le code source de `microsoft/AL-Go-Actions/IncrementVersionNumber@v9.2` (`IncrementVersionNumber.ps1`) : l'incrément `+0.0.1` n'est autorisé que si `($settings.versioningStrategy -band 15) -eq 3`, sinon l'action échoue avec `"Incremental version number +0.0.1 is not allowed. Allowed incremental version numbers are: +1, +0.1"`. Sans ce réglage, ni cette fonctionnalité ni la suivante ne peuvent fonctionner avec le défaut `+0.0.1`.

## Workflow `Auto Increment On CICD` (ajouté le 15/09/2026, ⚠️ non testé)

`.github/workflows/AutoIncrementOnCICD.yaml` — fait avancer automatiquement `app.json` sur la branche de développement à **chaque** réussite de CI/CD, indépendamment de toute release. Complète `Auto Release On Merge` (qui ne bump la branche de dev qu'une seule fois, juste après une release) par un incrément continu au fil du développement.

### Fonctionnement

- Se déclenche sur `workflow_run: workflows: ['CI/CD'], types: [completed]`, filtré par `if: conclusion == 'success'` — volontairement pas de filtre statique par branche ici (`CICD.yaml` s'en occupe déjà via son propre `on.push.branches`), le filtrage par branche pour l'incrément se fait à l'intérieur du job.
- Lit `.AL-Go/settings.json` → `autoIncrementOnCICD` :
  ```json
  "autoIncrementOnCICD": {
    "enabled": false,
    "branches": [ "develop" ],
    "versionIncrement": "+0.0.1"
  }
  ```
  - `enabled: false` par défaut.
  - `branches` : **volontairement une liste précise, pas "toutes les branches"** — sur une branche perso de développeur, chacune bumperait son propre `app.json` indépendamment, garantissant des conflits à la fusion. `"develop"` est un nom générique par défaut, **à adapter au nom réel de votre branche de développement partagée**.
  - `versionIncrement` : même valeur/rôle que sur `Auto Release On Merge`, défaut `"+0.0.1"`.
- **`CICD.yaml` doit déclencher `push` sur cette branche** pour que ce workflow ait quoi que ce soit à réagir — `develop` a été ajoutée à `on.push.branches` dans `CICD.yaml` en conséquence (à ajuster si votre branche a un autre nom).

### ⚠️ Risque de boucle infinie — comment il est évité

Ce workflow, à chaque incrément réussi, fait un commit direct (`directCommit: true`) sur la branche surveillée — et `CICD.yaml` déclenche `push` sur cette même branche, sans exclure `app.json` de son `paths-ignore`. Sans protection, ce commit **redéclenche la CI/CD**, qui en réussissant redéclenche un nouvel incrément, indéfiniment.

En lisant le code source de l'action (`IncrementVersionNumber.ps1`, v9.2), le message de commit qu'elle produit est **toujours** l'un des deux suivants, sans aucun marqueur `[skip ci]` :
- `"Incremented Version number by <valeur>"` (incrément relatif, ex. `+0.0.1`)
- `"New Version number <valeur>"` (valeur absolue)

Le job vérifie donc `github.event.workflow_run.head_commit.message` et **s'arrête sans rien faire** si ce message correspond à l'un de ces deux formats — évite la boucle sans avoir à modifier l'action Microsoft elle-même.

**⚠️ Non testé en conditions réelles** — comme le reste de cette série de workflows. Le garde-fou anti-boucle repose sur un texte de commit observé dans le code source actuel (v9.2) de l'action Microsoft ; à revalider si vous montez de version d'AL-Go.

### ⚠️ Point de vigilance majeur

Une fois `enabled: true` (sur `Auto Release On Merge` et/ou `Auto Increment On CICD`), des commits/releases/déploiements automatiques peuvent se produire sans validation humaine supplémentaire — plus radical que tout ce qu'on a construit jusqu'ici. À activer uniquement en connaissance de cause, et à tester d'abord sur un dépôt/branche non-critique avant un usage réel.
