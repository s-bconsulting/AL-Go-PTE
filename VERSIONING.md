# Versioning et releases avec AL-Go

Ce document explique comment les numéros de version fonctionnent dans ce dépôt AL-Go, pour éviter les confusions entre la version de l'app, le tag de release GitHub et le numéro de build.

## 1. Structure d'une version d'extension Business Central

Une version d'app BC a toujours 4 segments : **Major.Minor.Build.Revision** (ex: `1.1.4.0`).

| Segment | D'où il vient |
| --- | --- |
| Major | `version` dans `app.json` (1er segment) |
| Minor | `version` dans `app.json` (2e segment) |
| Build | **Calculé automatiquement par AL-Go**, pas lu depuis `app.json` |
| Revision | **Calculé automatiquement par AL-Go**, pas lu depuis `app.json` |

Ce que vous écrivez dans `app.json` pour Build et Revision (ex: le `.0.0` dans `1.1.0.0`) est **ignoré** au moment de la compilation en CI/CD — seuls Major et Minor sont réellement utilisés.

## 2. Comment Build et Revision sont calculés (`versioningStrategy`)

Contrôlé par le paramètre `versioningStrategy` dans `.AL-Go/settings.json` (actuellement `0` sur ce dépôt = comportement par défaut) :

| Valeur | Build | Revision |
| --- | --- | --- |
| `0` (défaut) | Numéro de run GitHub Actions du workflow **CI/CD** (`github.run_number`, + `runNumberOffset` si défini) | `run_attempt - 1` (donc 0, sauf relance manuelle du même run) |
| `2` | Date UTC du jour (`yyyyMMdd`) | Heure UTC (`hhmmss`) |
| `3` | Vient d'`app.json` | Numéro de run GitHub Actions |
| `15` | Valeur maximale fixe | Numéro de run GitHub Actions |
| `+16` | (modificateur) Utilise `repoVersion` au lieu de Major.Minor d'`app.json` | |

**Point important sur la valeur `0`** : `github.run_number` est propre à **chaque fichier de workflow** — ce n'est pas un compteur global du dépôt. Donc Build correspond au nombre de fois où le workflow **CI/CD.yaml** précisément a tourné (pas CreateRelease, pas les autres). C'est pour ça que Build peut sembler "sauter" des valeurs ou ne pas correspondre à ce qu'on imaginerait intuitivement.

*Si vous voulez que Build corresponde exactement au 3e segment d'`app.json`, passez `versioningStrategy` à `3`.*

## 3. Le tag de release GitHub ≠ la version de l'app

Quand vous lancez le workflow **Create release**, le champ **tag** (ex: `1.0.0`) est :
- Un identifiant **GitHub uniquement**, au format semver à 3 segments (`Major.Minor.Patch`, voir https://semver.org).
- **Totalement indépendant** de la version 4 segments embarquée dans le `.app`.
- **Jamais rempli automatiquement** par AL-Go (`default: ''` dans le workflow) — c'est à vous de le saisir à chaque fois.

Pourquoi ce découplage : un dépôt peut contenir plusieurs projets/apps (ici `AllGoSample` + `AllGoSample.Test`), chacun avec son propre `app.json` et potentiellement sa propre version. AL-Go ne peut donc pas décider "LA" version à utiliser pour un tag global.

**Convention à suivre** : à chaque `Create release`, tapez le tag pour qu'il corresponde au Major.Minor de l'`app.json` de l'app principale — ex. `app.json` en `1.1.0.0` → tag `1.1.0`. Si vous refaites une release sans bump de version, incrémentez le patch (`1.1.1`, `1.1.2`, ...).

## 4. Bonnes pratiques

1. **Avant de créer une release**, mettez à jour `version` dans `app.json` (manuellement, ou via le workflow **Increment Version Number** / le champ `updateVersionNumber` de `Create release`).
2. **Au moment de `Create release`**, saisissez un tag qui reflète le Major.Minor de cet `app.json` (voir §3).
3. Ne vous fiez pas au segment Build (3e chiffre) de la version compilée pour "savoir où vous en êtes" — c'est un numéro technique lié aux runs CI/CD, pas une information métier.
4. Si vous voulez un Build prévisible et aligné sur `app.json`, changez `versioningStrategy` à `3` dans `.AL-Go/settings.json`.
5. Une release GitHub ne peut pas être recréée sur un commit qui a déjà une release existante — si besoin de retester, supprimez l'ancienne release (et son tag) ou utilisez un nouveau tag.
