# La Zone 2Keh — Unban

Application Flask de recours de bannissement avec notification Discord et espace d'administration.

## Déploiement rapide sur Render
1. Créer un **Web Service** depuis ce dépôt.
2. Runtime : **Python 3**.
3. Build command : `pip install -r requirements.txt`
4. Start command : `gunicorn app:app --bind 0.0.0.0:$PORT`
5. Ajouter les variables :
   - `SECRET_KEY` : longue valeur aléatoire.
   - `ADMIN_PASSWORD` : mot de passe fort du panel.
   - `DISCORD_WEBHOOK_URL` : webhook du salon de réception.
6. Déployer. Le formulaire est sur `/`, le panel sur `/admin/login`.

## Données et sécurité
SQLite est utilisé pour cette version de démonstration. Sur Render, le système de fichiers standard est éphémère : les données peuvent disparaître lors d'un redéploiement ou redémarrage. Pour une utilisation durable, configurer un disque persistant ou PostgreSQL.
Les IP sont collectées pour la sécurité et accessibles aux administrateurs. La géolocalisation et la détection VPN ne sont pas activées. Définir une durée de conservation et informer les visiteurs avant une mise en production.
