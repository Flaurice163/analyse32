# Version Windows (.exe)

L’application est fournie comme une application Streamlit locale : le
lancement de l’exécutable démarre un serveur accessible uniquement sur ce PC
et ouvre l’interface dans le navigateur à l’adresse `http://localhost:8501`.

## Construire l’exécutable

Depuis le dossier du projet, dans PowerShell :

```powershell
python -m pip install -r requirements-build.txt
.\build_windows.ps1
```

Le résultat est `dist\AnalysePME\AnalysePME.exe`. Distribuez le dossier
`dist\AnalysePME` en entier, et non le seul fichier `.exe`.

## Configurer Supabase sur le PC

Créez `dist\AnalysePME\.streamlit\secrets.toml` à côté de
`AnalysePME.exe` :

```toml
[supabase]
url = "https://VOTRE-PROJET.supabase.co"
anon_key = "VOTRE_CLE_PUBLISHABLE"

[app]
public_url = "http://localhost:8501"
```

Ne mettez jamais de clé `service_role` dans cette configuration. Le fichier
`secrets.toml` est privé et doit être configuré sur chaque PC; il n’est pas
inclus dans le paquet. Le PC doit avoir accès à Internet pour joindre Supabase.

Gardez la fenêtre du programme ouverte pendant l’utilisation. Fermez-la pour
arrêter le serveur local.
