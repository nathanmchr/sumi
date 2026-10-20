# Sessions et reprise après expiration

Le jeton d’accès expire après 60 minutes dans la configuration locale ; le cookie de renouvellement dure 14 jours. Ces durées et les protections HttpOnly/SameSite/Secure configurées restent inchangées. Le défaut corrigé était l’absence d’appel de renouvellement côté navigateur, malgré un endpoint `/auth/refresh` déjà disponible.

## Requête protégée

Une réponse HTTP 401 entraîne un renouvellement, puis une seule reprise de la requête originale avec le même corps. Les erreurs réseau et HTTP 5xx ne déclenchent pas de renvoi automatique d’une écriture : elle pourrait déjà avoir été acceptée.

Les requêtes d’un onglet partagent la même promesse de renouvellement. Avec Web Locks, les onglets de la même origine sérialisent leurs opérations d’authentification ; une vérification de session sous le verrou évite de renouveler un cookie qu’un autre onglet vient déjà de remplacer. Le compteur local de renouvellement couvre les réponses 401 arrivant en retard. Sans Web Locks, la mutualisation reste locale à l’onglet ; une rotation concurrente refusée conduit au mécanisme de reconnexion plutôt qu’à la réutilisation d’un ancien jeton.

La connexion, l’inscription, la déconnexion et le renouvellement ne déclenchent pas de boucle de renouvellement. Une déconnexion ou une connexion explicite invalide la reprise des anciennes requêtes en attente. Le compte obtenu au renouvellement est vérifié avant toute reprise : une requête refusée pour l’ancien compte ne doit pas être rejouée sous un autre compte connecté dans un autre onglet.

## Reconnexion sans abandon de la page

Un refus d’authentification définitif après une session connue conserve les données SWR et les composants de la page. Une boîte de dialogue demande le mot de passe du même compte. La page et les champs restent montés ; un mauvais mot de passe ou une indisponibilité du réseau ne les efface pas. Après reconnexion, la réponse non enregistrée peut être validée de nouveau. Le dialogue est aussi disponible aux autres pages utilisant le client API partagé.

Au premier accès sans session connue et sans cookie renouvelable, le flux normal de connexion reste utilisé. La déconnexion volontaire continue de vider les caches et de quitter l’espace connecté.

## Rotation côté serveur

La ligne du jeton est verrouillée avant de vérifier sa révocation. La révocation de l’ancien jeton et l’émission du suivant sont dans la même transaction ; un échec avant l’émission n’invalide pas le seul jeton encore utilisable. Un jeton malformé, expiré, révoqué, du mauvais type ou appartenant à un compte désactivé renvoie 401. La suppression des cookies utilise les mêmes paramètres de domaine et de chemin que leur création.

## Progression des leçons

Chaque réponse et chaque continuation est déjà enregistrée en base, indépendamment de la fin de la leçon. Une requête rejetée à l’authentification ne modifie pas le curseur. Après renouvellement, elle est reprise avec sa révision d’origine ; l’idempotence existante évite de compter deux fois une commande déjà enregistrée. La progression validée se retrouve après rechargement ou nouvelle connexion.

La saisie non soumise reste en mémoire dans la page pendant la reconnexion. Ce mécanisme ne constitue pas une sauvegarde persistante du brouillon après fermeture ou rechargement de l’onglet.

## Vérifications

- `cd backend && AUTH_TEST_POSTGRES=1 .venv/bin/python -m unittest discover -s tests -p test_auth_session.py -q` : 13 tests SQLite/PostgreSQL, schémas temporaires, cookies réels, rotation concurrente, rollback, expiration, déconnexion et reprise de leçon.
- `cd frontend && node --test tests/auth-refresh.test.cjs` : 9 tests du client API réel, renouvellement partagé, deux onglets, réponse tardive, erreurs réseau, changement de compte et déconnexion.
- `frontend/tests/session-recovery.browser.js` : scénario WebKit à réponses simulées, expiration pendant la saisie, renouvellement et enregistrement uniques, reconnexion avec mauvais puis bon mot de passe, champ conservé, panne réseau, reprise après rechargement, déconnexion volontaire. Capture : `output/playwright/session-reconnect-mobile.png`.
- TypeScript valide ; suite leçons : 58 tests, dont 39 réussis et 19 opt-in ignorés.

Aucune session réelle n’a été expirée volontairement, aucune progression utilisateur n’a été modifiée et les serveurs n’ont pas été relancés manuellement pour ces tests.
