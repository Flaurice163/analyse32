# Configuration Supabase

L’application utilise Supabase Auth pour les comptes e-mail/mot de passe et
une ligne privée par utilisateur dans PostgreSQL. Les données de ventes,
produits, catalogue et objectifs ne sont pas partagées entre les comptes.

1. Dans le tableau de bord Supabase, ouvrez **SQL Editor**, puis exécutez le
   contenu de `supabase_schema.sql`.
2. Dans **Authentication → Providers → Email**, activez l’authentification
   par e-mail. Si la confirmation d’adresse est activée, chaque nouvel
   utilisateur devra confirmer son adresse avant de se connecter.
3. Récupérez l’URL du projet et sa clé `anon`/publishable dans **Project
   Settings → API**.
4. Créez `.streamlit/secrets.toml` dans le dossier du projet :

   ```toml
   [supabase]
   url = "https://VOTRE-PROJET.supabase.co"
   anon_key = "VOTRE_CLE_ANON"
   ```

5. Installez les dépendances avec `pip install -r requirements.txt`, puis
   démarrez l’application avec `streamlit run app_ventes.py`.

N’utilisez jamais la clé `service_role` dans l’application ou dans
`secrets.toml`. Les politiques RLS du schéma limitent chaque session aux
données associées à son propre identifiant Auth. Le fichier `secrets.toml`
contient des identifiants privés et ne doit pas être partagé.

Les anciens fichiers CSV locaux ne sont pas importés automatiquement.
Après connexion, utilisez **Import / Export** pour importer vos fichiers de
ventes dans votre compte.
