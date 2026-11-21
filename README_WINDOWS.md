# Installateur Windows

L’installateur crée une application Windows avec sa propre fenêtre, sans
ouvrir de navigateur externe. La fenêtre affiche la version hébergée à
`https://analyse-pme.streamlit.app/`; une connexion Internet est donc
nécessaire. Les données et comptes continuent d’utiliser Supabase.

## Construire l’installateur

Installez [Inno Setup 6](https://jrsoftware.org/isinfo.php), puis exécutez
PowerShell depuis le dossier du projet :

```powershell
python -m pip install -r requirements-build.txt
.\build_windows.ps1
```

Le résultat est `dist\Installateur\AnalysePME-Setup.exe`. Cet installateur
déploie l’application, installe le composant Microsoft Edge WebView2 requis
pour sa fenêtre intégrée, et propose des raccourcis du menu Démarrer et du
Bureau.

## Installer sur un autre PC

Copiez `AnalysePME-Setup.exe` sur le PC cible et exécutez-le. L’installation
de l’application et de WebView2 requiert une connexion Internet et des droits
d’administrateur. Une fois installée, l’application requiert Internet pour
afficher le service hébergé.
