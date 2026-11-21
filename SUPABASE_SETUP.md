# Configuration Supabase

L’application utilise Supabase Auth pour les comptes e-mail/mot de passe et
une ligne privée par utilisateur dans PostgreSQL. Les données de ventes,
produits, catalogue et objectifs ne sont pas partagées entre les comptes.

1. Dans le tableau de bord Supabase, ouvrez **SQL Editor**, puis exécutez le
   contenu actualisé de `supabase_schema.sql`. Si vous aviez déjà exécuté
   l’ancienne version, relancez ce script : il ajoute la colonne nécessaire
   pour enregistrer vos boutiques sans supprimer vos données existantes.
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

   En production, vous pouvez définir l’adresse de retour publique de
   l’application pour les e-mails de réinitialisation :

   ```toml
   [app]
   public_url = "https://votre-application.example.com"
   ```

   En développement, l’application utilise automatiquement l’adresse
   Streamlit courante.

5. Pour que le lien « Mot de passe oublié » ouvre le formulaire de changement
   dans l’application, ajoutez l’adresse de l’application à **Authentication
   → URL Configuration → Redirect URLs**, puis ouvrez **Authentication →
   Email Templates → Reset Password** et utilisez un lien de ce type dans le
   modèle :

   ```html
   <a href="{{ .RedirectTo }}?token_hash={{ .TokenHash }}&amp;type=recovery">
     Réinitialiser mon mot de passe
   </a>
   ```

   Le lien contient un jeton à usage unique, vérifié par Supabase Auth avant
   d’autoriser le nouveau mot de passe. Ne transmettez pas le mot de passe par
   e-mail.

6. Installez les dépendances avec `pip install -r requirements.txt`, puis
   démarrez l’application avec `streamlit run app_ventes.py`.

N’utilisez jamais la clé `service_role` dans l’application ou dans
`secrets.toml`. Les politiques RLS du schéma limitent chaque session aux
données associées à son propre identifiant Auth. Le fichier `secrets.toml`
contient des identifiants privés et ne doit pas être partagé.

Les anciens fichiers CSV locaux ne sont pas importés automatiquement.
Après connexion, utilisez **Import / Export** pour importer vos fichiers de
ventes dans votre compte.
