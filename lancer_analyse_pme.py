import os
import sys
from pathlib import Path

from streamlit.web.cli import main


def main_local():
    dossier_distribution = (
        Path(sys.executable).resolve().parent
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parent
    )
    application = (
        Path(getattr(sys, "_MEIPASS", dossier_distribution)) / "app_ventes.py"
    )
    if not application.is_file():
        raise FileNotFoundError(f"Fichier de l’application introuvable : {application}")

    os.chdir(dossier_distribution)
    sys.argv = [
        "streamlit",
        "run",
        str(application),
        "--server.address=127.0.0.1",
        "--server.port=8501",
        "--server.headless=false",
        "--browser.gatherUsageStats=false",
    ]
    main()


if __name__ == "__main__":
    main_local()
