import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, datetime, timedelta
import json
from urllib.parse import urlsplit, urlunsplit
from httpx import HTTPError
from postgrest.exceptions import APIError
from supabase_auth.errors import AuthError
from streamlit.errors import StreamlitSecretNotFoundError
from supabase import Client, create_client

# ===================== CONFIG =====================
px.defaults.template = "plotly_dark"
st.set_page_config(
    page_title="Analyse des ventes",
    layout="wide",
    page_icon=":material/monitoring:",
)

TABLE_ESPACE = "ventes_workspace"
COLONNES_VENTES = ["Magasin", "Mois", "Semaine", "Annee", "Jour", "Ventes", "Date", "DateVente", "Cout", "Canal"]
COLONNES_PRODUITS = ["DateVente", "Magasin", "Produit", "Categorie", "Quantite", "Prix unitaire", "Canal", "Date"]
COLONNES_CATALOGUE = ["Produit", "Categorie"]
COLONNES_OBJECTIFS = ["Magasin", "Mois", "Objectif"]
COLONNES_MAGASINS = ["Magasin"]
CHAMPS_ESPACE = {
    "df": ("ventes_journalieres", COLONNES_VENTES),
    "ventes_produits": ("ventes_produits", COLONNES_PRODUITS),
    "catalogue_produits": ("catalogue_produits", COLONNES_CATALOGUE),
    "objectifs": ("objectifs", COLONNES_OBJECTIFS),
    "magasins": ("magasins", COLONNES_MAGASINS),
}
JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
MOIS_FR = [
    "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
]

# ===================== FONCTIONS =====================
def _executer_requete(requete):
    try:
        return requete.execute()
    except (APIError, HTTPError) as erreur:
        st.error(f"Erreur de communication avec Supabase : {erreur}")
        st.stop()

def _creer_client_supabase():
    try:
        configuration = st.secrets["supabase"]
        url = str(configuration["url"]).strip()
        cle_anon = str(configuration["anon_key"]).strip()
    except (KeyError, StreamlitSecretNotFoundError):
        st.error("La configuration Supabase est manquante.")
        st.markdown(
            "Ajoutez `url` et `anon_key` dans `.streamlit/secrets.toml`, "
            "puis exécutez le script SQL `supabase_schema.sql` dans l’éditeur SQL Supabase."
        )
        st.code(
            '[supabase]\nurl = "https://VOTRE-PROJET.supabase.co"\nanon_key = "VOTRE_CLE_ANON"',
            language="toml",
        )
        st.stop()
    if not url or not cle_anon:
        st.error("L’URL et la clé anon Supabase doivent être renseignées.")
        st.stop()
    return create_client(url, cle_anon)

def _charger_espace(client: Client, user_id: str):
    _executer_requete(
        client.table(TABLE_ESPACE).upsert(
            {"user_id": user_id}, on_conflict="user_id"
        )
    )
    resultat = _executer_requete(
        client.table(TABLE_ESPACE)
        .select("ventes_journalieres, ventes_produits, catalogue_produits, objectifs, magasins")
        .eq("user_id", user_id)
        .limit(1)
    )
    if not resultat.data:
        st.error("L’espace Supabase de cet utilisateur n’a pas pu être chargé.")
        st.stop()
    espace = resultat.data[0]
    return {
        cle: pd.DataFrame(espace.get(champ) or [], columns=colonnes)
        for cle, (champ, colonnes) in CHAMPS_ESPACE.items()
    }

def _sauvegarder_section(cle: str, df: pd.DataFrame):
    champ, colonnes = CHAMPS_ESPACE[cle]
    contenu = json.loads(
        df.reindex(columns=colonnes).to_json(orient="records", date_format="iso")
    )
    utilisateur = st.session_state.supabase_user
    client = st.session_state.supabase_client
    resultat = _executer_requete(
        client.table(TABLE_ESPACE)
        .update({champ: contenu, "updated_at": datetime.now().astimezone().isoformat()})
        .eq("user_id", utilisateur["id"])
    )
    if not resultat.data:
        st.error("Aucune donnée n’a été enregistrée dans l’espace Supabase.")
        st.stop()

def sauvegarder_donnees(df):
    _sauvegarder_section("df", df)

def sauvegarder_ventes_produits(df):
    _sauvegarder_section("ventes_produits", df)

def sauvegarder_catalogue(df):
    _sauvegarder_section("catalogue_produits", df)

def sauvegarder_objectifs(df):
    _sauvegarder_section("objectifs", df)

def sauvegarder_magasins(df):
    _sauvegarder_section("magasins", df)

def lister_magasins():
    noms = []
    for source in [
        st.session_state.magasins["Magasin"],
        st.session_state.df["Magasin"],
        st.session_state.ventes_produits["Magasin"],
    ]:
        noms.extend(source.dropna().astype(str).str.strip().tolist())
    uniques = {nom.casefold(): nom for nom in noms if nom}
    return sorted(uniques.values(), key=str.casefold) or ["Principal"]

def normaliser_ventes(df):
    df = df.copy()
    ventes = pd.to_numeric(df["Ventes"], errors="coerce")
    invalides = df["Ventes"].notna() & ventes.isna()
    df["Ventes"] = ventes
    dates = pd.to_datetime(df["DateVente"], errors="coerce")
    annees = pd.to_numeric(df["Annee"], errors="coerce")
    df["Annee"] = dates.dt.year.fillna(annees).astype("Int64")
    return df, int(invalides.sum())

def construire_journal(df, ventes_produits):
    journal = df.copy()
    journal["Ventes"] = pd.to_numeric(journal["Ventes"], errors="coerce")
    journal["Cout"] = pd.to_numeric(journal["Cout"], errors="coerce")
    journal["DateVente"] = pd.to_datetime(journal["DateVente"], errors="coerce").dt.normalize()
    journal = journal[journal["Ventes"].notna()].copy()
    journal["_cle_date"] = journal["DateVente"].dt.strftime("%Y-%m-%d")
    jours_deja_saisis = set(
        zip(journal.loc[journal["_cle_date"].notna(), "Magasin"].astype(str),
            journal.loc[journal["_cle_date"].notna(), "_cle_date"])
    )

    lignes = ventes_produits.copy()
    if not lignes.empty:
        lignes["DateVente"] = pd.to_datetime(lignes["DateVente"], errors="coerce").dt.normalize()
        lignes["Quantite"] = pd.to_numeric(lignes["Quantite"], errors="coerce")
        lignes["Prix unitaire"] = pd.to_numeric(lignes["Prix unitaire"], errors="coerce")
        lignes["Ventes"] = lignes["Quantite"] * lignes["Prix unitaire"]
        lignes = lignes.dropna(subset=["DateVente", "Magasin", "Ventes"])
        resume = lignes.groupby(["DateVente", "Magasin"], as_index=False).agg(
            Ventes=("Ventes", "sum"),
            Canal=("Canal", lambda valeurs: ", ".join(sorted(set(valeurs.dropna().astype(str))))),
        )
        resume["_cle_date"] = resume["DateVente"].dt.strftime("%Y-%m-%d")
        resume = resume[
            ~resume.apply(
                lambda ligne: (str(ligne["Magasin"]), ligne["_cle_date"]) in jours_deja_saisis,
                axis=1,
            )
        ].copy()
        if not resume.empty:
            resume["Mois"] = resume["DateVente"].apply(
                lambda valeur: f"{MOIS_FR[valeur.month - 1]} {valeur.year}"
            )
            resume["Semaine"] = resume["DateVente"].apply(
                lambda valeur: f"S{valeur.isocalendar().week}"
            )
            resume["Annee"] = resume["DateVente"].dt.year
            resume["Jour"] = resume["DateVente"].dt.day_name()
            jours_en = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            traductions = dict(zip(jours_en, JOURS))
            resume["Jour"] = resume["Jour"].map(traductions)
            resume["Date"] = resume["DateVente"].dt.strftime("%Y-%m-%d")
            resume["Cout"] = pd.NA
            journal = pd.concat([journal, resume], ignore_index=True, sort=False)

    journal["DateVente"] = pd.to_datetime(journal["DateVente"], errors="coerce").dt.normalize()
    journal["Ventes"] = pd.to_numeric(journal["Ventes"], errors="coerce")
    journal["Cout"] = pd.to_numeric(journal["Cout"], errors="coerce")
    return journal.drop(columns=["_cle_date"], errors="ignore")

def filtrer_periode(donnees, debut=None, fin=None):
    if debut is None or fin is None:
        return donnees.copy()
    dates = pd.to_datetime(donnees["DateVente"], errors="coerce")
    return donnees[dates.between(pd.Timestamp(debut), pd.Timestamp(fin), inclusive="both")].copy()

def detecter_doublons_journaliers(donnees):
    cles = []
    for _, ligne in donnees.iterrows():
        magasin = str(ligne.get("Magasin", "")).strip().casefold()
        date_vente = pd.to_datetime(ligne.get("DateVente"), errors="coerce")
        if pd.notna(date_vente):
            cles.append(("date", magasin, date_vente.strftime("%Y-%m-%d")))
        else:
            cles.append((
                "periode",
                magasin,
                str(ligne.get("Mois", "")).strip().casefold(),
                str(ligne.get("Semaine", "")).strip().casefold(),
                str(ligne.get("Jour", "")).strip().casefold(),
            ))
    comptes = pd.Series(cles).value_counts()
    masque = pd.Series(cles).map(comptes).gt(1)
    return donnees.loc[masque.to_numpy()].copy()

def ajouter_filtres_periode(donnees, cle):
    dates = pd.to_datetime(donnees["DateVente"], errors="coerce").dropna()
    activer = st.checkbox("Limiter par date de vente", key=f"{cle}_activer_date")
    if not activer:
        return None, None
    if dates.empty:
        st.info("Aucune date de vente renseignée. Les lignes historiques doivent être datées pour utiliser ce filtre.")
        return None, None
    debut_min, fin_max = dates.min().date(), dates.max().date()
    colonnes = st.columns(2)
    debut = colonnes[0].date_input(
        "Du", value=debut_min, min_value=debut_min, max_value=fin_max, key=f"{cle}_debut"
    )
    fin = colonnes[1].date_input(
        "Au", value=fin_max, min_value=debut_min, max_value=fin_max, key=f"{cle}_fin"
    )
    if debut > fin:
        st.error("La date de début doit précéder la date de fin.")
        return debut, debut
    return debut, fin

def valider_import_journal(import_df, existants):
    resultat = import_df.copy()
    obligatoires = ["Magasin", "Mois", "Semaine", "Jour", "Ventes"]
    manquantes = [colonne for colonne in obligatoires if colonne not in resultat]
    if manquantes:
        return pd.DataFrame(columns=COLONNES_VENTES), [
            f"Colonnes obligatoires absentes : {', '.join(manquantes)}."
        ], 0
    for colonne in COLONNES_VENTES:
        if colonne not in resultat:
            resultat[colonne] = pd.NA

    erreurs = []
    lignes_invalides = pd.Series(False, index=resultat.index)
    ventes = pd.to_numeric(resultat["Ventes"], errors="coerce")
    invalides = resultat["Ventes"].isna() | ventes.isna() | (ventes < 0)
    if invalides.any():
        erreurs.append(f"{int(invalides.sum())} vente(s) vide(s), non numérique(s) ou négative(s).")
        lignes_invalides |= invalides
    resultat["Ventes"] = ventes

    couts_bruts = resultat["Cout"]
    couts = pd.to_numeric(couts_bruts, errors="coerce")
    couts_invalides = couts_bruts.notna() & (couts.isna() | (couts < 0))
    if couts_invalides.any():
        erreurs.append(f"{int(couts_invalides.sum())} coût(s) invalide(s).")
        lignes_invalides |= couts_invalides
    resultat["Cout"] = couts

    champs_vides = resultat[["Magasin", "Mois", "Semaine", "Jour"]].apply(
        lambda colonne: colonne.isna() | colonne.astype(str).str.strip().eq("")
    ).any(axis=1)
    if champs_vides.any():
        erreurs.append(f"{int(champs_vides.sum())} ligne(s) sans magasin, mois, semaine ou jour.")
        lignes_invalides |= champs_vides

    dates_brutes = resultat["DateVente"]
    dates = pd.to_datetime(dates_brutes, errors="coerce")
    dates_invalides = dates_brutes.notna() & dates.isna()
    if dates_invalides.any():
        erreurs.append(f"{int(dates_invalides.sum())} date(s) de vente invalide(s).")
        lignes_invalides |= dates_invalides
    resultat["DateVente"] = dates.dt.strftime("%Y-%m-%d")
    resultat["Annee"] = dates.dt.year
    resultat = resultat.loc[~lignes_invalides].copy()
    resultat["Date"] = resultat["Date"].fillna(datetime.now().strftime("%Y-%m-%d %H:%M"))
    resultat = resultat[COLONNES_VENTES]

    def cles_ligne(ligne):
        magasin = str(ligne["Magasin"]).strip().casefold()
        cles = []
        if pd.notna(ligne["DateVente"]):
            cles.append(("date", magasin, str(ligne["DateVente"])[:10]))
        if all(pd.notna(ligne[colonne]) for colonne in ["Mois", "Semaine", "Jour"]):
            cles.append((
                "periode",
                magasin,
                str(ligne["Mois"]).strip().casefold(),
                str(ligne["Semaine"]).strip().casefold(),
                str(ligne["Jour"]).strip().casefold(),
            ))
        return cles

    existants = existants.reindex(columns=COLONNES_VENTES)
    cles_existantes = {
        cle
        for _, ligne in existants.iterrows()
        for cle in cles_ligne(ligne)
    }
    cles_import = resultat.apply(cles_ligne, axis=1)
    cles_import_vues = set()
    doublons_masque = []
    for cles in cles_import:
        doublon = any(cle in cles_existantes or cle in cles_import_vues for cle in cles)
        doublons_masque.append(doublon)
        cles_import_vues.update(cles)
    doublons = pd.Series(doublons_masque, index=resultat.index)
    nombre_doublons = int(doublons.sum())
    return resultat.loc[~doublons].reset_index(drop=True), erreurs, nombre_doublons

def valider_import_produits(import_df, existants):
    resultat = import_df.copy()
    obligatoires = ["DateVente", "Magasin", "Produit", "Quantite", "Prix unitaire", "Canal"]
    manquantes = [colonne for colonne in obligatoires if colonne not in resultat]
    if manquantes:
        return pd.DataFrame(columns=COLONNES_PRODUITS), [
            f"Colonnes obligatoires absentes : {', '.join(manquantes)}."
        ], 0
    for colonne in COLONNES_PRODUITS:
        if colonne not in resultat:
            resultat[colonne] = pd.NA
    erreurs = []
    lignes_invalides = pd.Series(False, index=resultat.index)
    for colonne in ["Quantite", "Prix unitaire"]:
        resultat[colonne] = pd.to_numeric(resultat[colonne], errors="coerce")
    valeurs_invalides = (
        resultat[["Quantite", "Prix unitaire"]].isna().any(axis=1)
        | (resultat["Quantite"] <= 0)
        | (resultat["Prix unitaire"] < 0)
    )
    if valeurs_invalides.any():
        erreurs.append(f"{int(valeurs_invalides.sum())} ligne(s) avec quantité ou prix invalide.")
        lignes_invalides |= valeurs_invalides
    dates = pd.to_datetime(resultat["DateVente"], errors="coerce")
    dates_invalides = dates.isna()
    if dates_invalides.any():
        erreurs.append(f"{int(dates_invalides.sum())} date(s) de vente invalide(s).")
        lignes_invalides |= dates_invalides
    resultat["DateVente"] = dates.dt.strftime("%Y-%m-%d")
    champs_vides = resultat[["Magasin", "Produit", "Canal"]].apply(
        lambda colonne: colonne.isna() | colonne.astype(str).str.strip().eq("")
    ).any(axis=1)
    if champs_vides.any():
        erreurs.append(f"{int(champs_vides.sum())} ligne(s) sans magasin, produit ou canal.")
        lignes_invalides |= champs_vides
    resultat["Categorie"] = resultat["Categorie"].fillna("Général")
    resultat["Date"] = resultat["Date"].fillna(datetime.now().strftime("%Y-%m-%d %H:%M"))
    resultat = resultat.loc[~lignes_invalides].copy()
    resultat = resultat[COLONNES_PRODUITS]
    cle = ["DateVente", "Magasin", "Produit", "Categorie", "Quantite", "Prix unitaire", "Canal"]
    existants = existants.reindex(columns=COLONNES_PRODUITS)
    cles_existantes = set(map(tuple, existants[cle].dropna(subset=["DateVente", "Magasin", "Produit"]).astype(str).to_numpy()))
    cles_import = resultat[cle].astype(str).apply(tuple, axis=1)
    doublons = cles_import.duplicated(keep="first") | cles_import.isin(cles_existantes)
    nombre_doublons = int(doublons.sum())
    return resultat.loc[~doublons].reset_index(drop=True), erreurs, nombre_doublons

def appliquer_style():
    st.markdown(
        """
        <style>
        :root {
            color-scheme: dark;
        }
        [data-testid="stAppViewContainer"] {
            background: #090b10;
            color: #f3f4f6;
        }
        [data-testid="stHeader"],
        [data-testid="stToolbar"],
        [data-testid="stStatusWidget"],
        [data-testid="stAppDeployButton"],
        [data-testid="stHeaderActionElements"],
        [data-testid="stFooter"],
        #MainMenu,
        footer {
            display: none !important;
        }
        [data-testid="stSidebar"] {
            background: #10141c;
            border-right: 1px solid #293241;
        }
        [data-testid="stSidebar"] * {
            color: #f3f4f6;
        }
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
            color: #aab4c3;
        }
        [data-testid="stSidebar"] button {
            min-height: 2.8rem;
            justify-content: flex-start;
            border: 1px solid #293241;
            border-radius: 0.65rem;
        }
        [data-testid="stSidebar"] button[kind="secondary"] {
            background: #151a23;
        }
        [data-testid="stSidebar"] button[kind="secondary"]:hover {
            background: #222b38;
            border-color: #3d4b5e;
        }
        [data-testid="stSidebar"] button[kind="primary"] {
            background: #1d4ed8;
            border-color: #3b82f6;
        }
        [data-testid="stMetric"] {
            padding: 1.1rem 1.2rem;
            background: #151a23;
            border: 1px solid #293241;
            border-radius: 0.85rem;
            box-shadow: 0 2px 12px rgba(0, 0, 0, 0.22);
        }
        [data-testid="stMetricLabel"] {
            color: #b4bfce;
        }
        [data-testid="stPlotlyChart"],
        [data-testid="stDataFrame"] {
            padding: 0.35rem;
            background: #11161e;
            border: 1px solid #293241;
            border-radius: 0.85rem;
        }
        h1, h2, h3 {
            color: #f8fafc;
            letter-spacing: -0.025em;
        }
        [data-testid="stMarkdownContainer"],
        [data-testid="stWidgetLabel"],
        [data-testid="stCaptionContainer"] {
            color: #e5e7eb;
        }
        [data-testid="stTextInput"] input,
        [data-testid="stNumberInput"] input,
        [data-testid="stDateInput"] input,
        [data-testid="stSelectbox"] [data-baseweb="select"] > div,
        [data-testid="stMultiSelect"] [data-baseweb="select"] > div,
        [data-testid="stFileUploader"] section {
            background: #151a23;
            color: #f3f4f6;
            border-color: #3b4656;
        }
        [data-testid="stDataFrame"] *,
        [data-testid="stTable"] * {
            color: #f3f4f6;
        }
        [data-testid="stTabs"] button {
            color: #d1d5db;
        }
        [data-testid="stTabs"] button[aria-selected="true"] {
            color: #93c5fd;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

# ===================== INITIALISATION =====================
appliquer_style()
client = st.session_state.get("supabase_client")
if client is None:
    client = _creer_client_supabase()

def _url_application():
    try:
        url_configuree = str(st.secrets["app"]["public_url"]).strip()
    except (KeyError, StreamlitSecretNotFoundError):
        url_configuree = st.context.url
    morceaux = urlsplit(url_configuree)
    if morceaux.scheme not in {"http", "https"} or not morceaux.netloc:
        st.error(
            "L’adresse publique de l’application est invalide. "
            "Configurez `[app].public_url` dans `.streamlit/secrets.toml`."
        )
        st.stop()
    return urlunsplit((morceaux.scheme, morceaux.netloc, morceaux.path, "", ""))

def _ouvrir_session(resultat_auth, email):
    if resultat_auth.user is None or resultat_auth.session is None:
        st.error("Supabase n’a pas ouvert de session. Vérifiez votre adresse e-mail.")
        return False
    st.session_state.supabase_client = client
    st.session_state.supabase_user = {
        "id": resultat_auth.user.id,
        "email": resultat_auth.user.email or email,
    }
    return True

type_retour = st.query_params.get("type", "")
token_hash = st.query_params.get("token_hash", "")
if token_hash and type_retour == "recovery":
    try:
        resultat_auth = client.auth.verify_otp(
            {"token_hash": token_hash, "type": "recovery"}
        )
    except (AuthError, HTTPError) as erreur:
        st.error(f"Le lien de réinitialisation est invalide ou expiré : {erreur}")
        st.query_params.clear()
        st.stop()
    if _ouvrir_session(resultat_auth, resultat_auth.user.email if resultat_auth.user else ""):
        st.session_state.mode_reinitialisation_mdp = True
        st.session_state.page = "Paramètres"
        st.query_params.clear()
        st.rerun()

if "supabase_user" not in st.session_state:
    _, colonne_auth, _ = st.columns([1, 1.15, 1])
    with colonne_auth:
        st.markdown(
            """
            <style>
            [data-testid="stMainBlockContainer"] {
                max-width: 1100px;
                padding-top: 2rem;
            }
            [data-testid="stForm"] {
                padding: 1.25rem;
                border: 1px solid #293241;
                border-radius: 1rem;
                background: linear-gradient(145deg, #151a23, #10141c);
            }
            [data-testid="stButton"] button {
                min-height: 2.8rem;
                border-radius: .7rem;
            }
            @media (max-width: 640px) {
                [data-testid="stMainBlockContainer"] {
                    padding: 1rem .75rem 2rem;
                }
                [data-testid="stForm"] {
                    padding: 1rem;
                }
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            """
            <div style="text-align:center; padding: 2rem 1.5rem 1.6rem;
                 margin-bottom:1.2rem; border:1px solid #293241; border-radius:1.2rem;
                 background:radial-gradient(ellipse at top, #1d3554 0%, #111722 65%);">
                <div style="display:inline-flex; align-items:center; gap:.6rem;
                     color:#93c5fd; font-weight:700; letter-spacing:.12em;
                     font-size:.8rem;">
                    <span class="material-symbols-rounded">monitoring</span>
                    ANALYSE PME
                </div>
                <h1 style="font-size:2.4rem; margin:.8rem 0 .35rem;">
                    Vos ventes, en perspective.
                </h1>
                <p style="color:#aab4c3; margin:0;">
                    Un espace sécurisé pour comprendre vos résultats et piloter votre activité.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        mode_auth = st.session_state.setdefault("mode_auth", "connexion")
        if mode_auth == "connexion":
            st.markdown("#### Bon retour")
            st.caption("Connectez-vous à votre espace d’analyse.")
            with st.form("formulaire_connexion"):
                email_connexion = st.text_input(
                    "Adresse e-mail", key="email_connexion"
                )
                mot_de_passe = st.text_input(
                    "Mot de passe",
                    type="password",
                    key="mot_de_passe_connexion",
                )
                connexion = st.form_submit_button(
                    "Se connecter",
                    type="primary",
                    icon=":material/login:",
                    use_container_width=True,
                )
            if connexion:
                try:
                    resultat_auth = client.auth.sign_in_with_password(
                        {"email": email_connexion.strip(), "password": mot_de_passe}
                    )
                except (AuthError, HTTPError) as erreur:
                    st.error(f"Connexion impossible : {erreur}")
                else:
                    if _ouvrir_session(resultat_auth, email_connexion.strip()):
                        st.rerun()
            st.divider()
            st.caption("Vous n’avez pas encore de compte ?")
            if st.button(
                "Créer un compte",
                icon=":material/person_add:",
                use_container_width=True,
                key="ouvrir_inscription",
            ):
                st.session_state.mode_auth = "inscription"
                st.rerun()
            if st.button(
                "Mot de passe oublié ?",
                icon=":material/lock_reset:",
                use_container_width=True,
                key="ouvrir_mdp_oublie",
            ):
                st.session_state.mode_auth = "mdp_oublie"
                st.rerun()

        elif mode_auth == "inscription":
            st.markdown("#### Créer votre espace")
            st.caption("Vos données resteront privées à votre compte.")
            with st.form("formulaire_inscription"):
                email_inscription = st.text_input(
                    "Adresse e-mail", key="email_inscription"
                )
                mot_de_passe_inscription = st.text_input(
                    "Mot de passe (8 caractères minimum)",
                    type="password",
                    key="mot_de_passe_inscription",
                )
                confirmation_mot_de_passe = st.text_input(
                    "Confirmer le mot de passe",
                    type="password",
                    key="confirmation_mot_de_passe",
                )
                inscription = st.form_submit_button(
                    "Créer mon compte",
                    type="primary",
                    icon=":material/person_add:",
                    use_container_width=True,
                )
            if inscription:
                if len(mot_de_passe_inscription) < 8:
                    st.error("Le mot de passe doit contenir au moins 8 caractères.")
                elif mot_de_passe_inscription != confirmation_mot_de_passe:
                    st.error("Les deux mots de passe ne correspondent pas.")
                elif not email_inscription.strip():
                    st.error("L’adresse e-mail est obligatoire.")
                else:
                    try:
                        resultat_auth = client.auth.sign_up(
                            {
                                "email": email_inscription.strip(),
                                "password": mot_de_passe_inscription,
                            }
                        )
                    except (AuthError, HTTPError) as erreur:
                        st.error(f"Création du compte impossible : {erreur}")
                    else:
                        if resultat_auth.user is None:
                            st.error("Supabase n’a pas retourné de compte utilisateur.")
                        elif resultat_auth.session is None:
                            st.success(
                                "Compte créé. Confirmez votre adresse e-mail depuis "
                                "le message envoyé par Supabase, puis connectez-vous."
                            )
                        elif _ouvrir_session(resultat_auth, email_inscription.strip()):
                            st.rerun()
            st.divider()
            if st.button(
                "Retour à la connexion",
                icon=":material/arrow_back:",
                use_container_width=True,
                key="retour_connexion_inscription",
            ):
                st.session_state.mode_auth = "connexion"
                st.rerun()

        else:
            st.markdown("#### Réinitialiser votre mot de passe")
            st.caption(
                "Nous vous enverrons un lien sécurisé pour choisir un nouveau mot de passe."
            )
            with st.form("formulaire_mdp_oublie"):
                email_reinitialisation = st.text_input(
                    "Adresse e-mail du compte", key="email_reinitialisation"
                )
                demander_reinitialisation = st.form_submit_button(
                    "Envoyer le lien de réinitialisation",
                    type="primary",
                    icon=":material/lock_reset:",
                    use_container_width=True,
                )
            if demander_reinitialisation:
                if not email_reinitialisation.strip():
                    st.error("Saisissez l’adresse e-mail de votre compte.")
                else:
                    try:
                        client.auth.reset_password_for_email(
                            email_reinitialisation.strip(),
                            {"redirect_to": _url_application()},
                        )
                    except (AuthError, HTTPError) as erreur:
                        st.error(f"Envoi du lien impossible : {erreur}")
                    else:
                        st.success(
                            "Si cette adresse correspond à un compte, un e-mail "
                            "de réinitialisation vient d’être envoyé."
                        )
                        st.info(
                            "Ouvrez le lien, puis définissez votre nouveau mot de passe "
                            "dans la page qui s’affichera."
                        )
            st.divider()
            if st.button(
                "Retour à la connexion",
                icon=":material/arrow_back:",
                use_container_width=True,
                key="retour_connexion_mdp_oublie",
            ):
                st.session_state.mode_auth = "connexion"
                st.rerun()
    st.stop()

utilisateur = st.session_state.supabase_user
if st.session_state.get("workspace_user_id") != utilisateur["id"]:
    espace = _charger_espace(client, utilisateur["id"])
    for cle, donnees in espace.items():
        st.session_state[cle] = donnees
    st.session_state.workspace_user_id = utilisateur["id"]
    st.session_state.page = (
        "Paramètres"
        if st.session_state.get("mode_reinitialisation_mdp")
        else "Tableau de bord"
    )

for colonne in COLONNES_VENTES:
    if colonne not in st.session_state.df:
        st.session_state.df[colonne] = pd.NA
df, lignes_ventes_invalides = normaliser_ventes(st.session_state.df)
if lignes_ventes_invalides:
    st.warning(
        f"{lignes_ventes_invalides} valeur(s) de ventes ne sont pas numériques. "
        "Elles sont exclues des calculs ; corrige-les dans Données & Édition."
    )
    df = df[df["Ventes"].notna()].copy()
else:
    st.session_state.df = df
ventes_produits = st.session_state.ventes_produits
journal = construire_journal(df, ventes_produits)

# ===================== SIDEBAR =====================
PAGES = [
    ("Tableau de bord", ":material/dashboard:"),
    ("Saisie des ventes", ":material/edit_note:"),
    ("Données importées", ":material/table_view:"),
    ("Objectifs", ":material/flag:"),
    ("Analyses", ":material/query_stats:"),
    ("Prévisions", ":material/show_chart:"),
    ("Import / Export", ":material/import_export:"),
    ("Paramètres", ":material/settings:"),
]

if "page" not in st.session_state:
    st.session_state.page = PAGES[0][0]
elif st.session_state.page not in {nom_page for nom_page, _ in PAGES}:
    st.session_state.page = PAGES[0][0]

with st.sidebar:
    st.markdown("### :material/monitoring:  ANALYSE PME")
    st.caption("PILOTAGE DES VENTES")
    st.divider()
    for nom_page, icone in PAGES:
        if st.button(
            nom_page,
            key=f"navigation_{nom_page}",
            icon=icone,
            type="primary" if st.session_state.page == nom_page else "secondary",
            use_container_width=True,
        ):
            st.session_state.page = nom_page
            st.rerun()
    st.divider()
    st.caption(f"{len(journal)} observations analysées")
    st.divider()
    st.caption(utilisateur["email"])
    if st.button("Se déconnecter", icon=":material/logout:", use_container_width=True):
        try:
            client.auth.sign_out()
        except (AuthError, HTTPError) as erreur:
            st.error(f"Déconnexion impossible : {erreur}")
        else:
            for cle in ["supabase_user", "supabase_client", "workspace_user_id"]:
                st.session_state.pop(cle, None)
            st.rerun()

page = st.session_state.page

# ===================== DASHBOARD =====================
if page == "Tableau de bord":
    st.title("Vue d’ensemble des ventes")
    st.caption("Analysez les tendances, comparez les périodes et suivez la performance commerciale.")
    confirmation_dashboard = st.session_state.pop(
        "confirmation_saisie_dashboard", None
    )
    if confirmation_dashboard and confirmation_dashboard["user_id"] == utilisateur["id"]:
        st.success(confirmation_dashboard["message"])
    confirmation_securite = st.session_state.pop("confirmation_securite", None)
    if confirmation_securite:
        st.success(confirmation_securite)
    
    magasins = sorted(journal["Magasin"].dropna().astype(str).unique())
    mois_disponibles = sorted(journal["Mois"].dropna().astype(str).unique())
    filtres = st.columns(2)
    with filtres[0]:
        magasins_selectionnes = st.multiselect(
            "Magasins", magasins, default=magasins, key="dashboard_magasins"
        )
    with filtres[1]:
        mois_selectionnes = st.multiselect(
            "Mois", mois_disponibles, default=mois_disponibles, key="dashboard_mois"
        )
    debut, fin = ajouter_filtres_periode(journal, "dashboard")
    donnees = journal[
        journal["Magasin"].astype(str).isin(magasins_selectionnes)
        & journal["Mois"].astype(str).isin(mois_selectionnes)
    ].copy()
    donnees = filtrer_periode(donnees, debut, fin)

    if donnees.empty:
        st.info("Aucune vente ne correspond aux filtres sélectionnés.")
    else:
        comparaison = st.checkbox(
            "Comparer à la période précédente", disabled=debut is None or fin is None
        )
        delta_revenu = None
        if comparaison and debut is not None and fin is not None:
            duree = (fin - debut).days + 1
            debut_precedent = debut - timedelta(days=duree)
            fin_precedent = debut - timedelta(days=1)
            precedentes = filtrer_periode(
                journal[journal["Magasin"].astype(str).isin(magasins_selectionnes)],
                debut_precedent,
                fin_precedent,
            )
            total_precedent = precedentes["Ventes"].sum()
            delta_revenu = (
                f"{(donnees['Ventes'].sum() / total_precedent - 1) * 100:+.1f}%"
                if total_precedent
                else "Pas de période de référence"
            )

        hebdomadaire = (
            donnees.groupby(
                ["Magasin", "Mois", "Annee", "Semaine"], as_index=False, dropna=False
            )["Ventes"]
            .sum()
            .rename(columns={"Ventes": "Total semaine"})
        )
        hebdomadaire["Ordre semaine"] = pd.to_numeric(
            hebdomadaire["Semaine"].astype(str).str.extract(r"(\d+)")[0],
            errors="coerce",
        )
        hebdomadaire = hebdomadaire.sort_values(
            ["Mois", "Ordre semaine", "Semaine", "Magasin"],
            na_position="last",
        ).reset_index(drop=True)
        hebdomadaire["Évolution (%)"] = (
            hebdomadaire.groupby(["Magasin", "Mois"])["Total semaine"].pct_change().mul(100)
        )
        hebdomadaire["Période"] = (
            hebdomadaire["Mois"].astype(str) + " · " + hebdomadaire["Semaine"].astype(str)
        )
        meilleure_semaine = hebdomadaire.loc[hebdomadaire["Total semaine"].idxmax()]
        couts_connus = donnees[donnees["Cout"].notna()]
        benefice = (couts_connus["Ventes"] - couts_connus["Cout"]).sum()
        marge = benefice / couts_connus["Ventes"].sum() * 100 if couts_connus["Ventes"].sum() else 0

        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric(":material/payments: Chiffre d’affaires", f"{donnees['Ventes'].sum():,.0f} €", delta=delta_revenu)
        col2.metric(":material/monitoring: Moyenne / jour", f"{donnees['Ventes'].mean():,.0f} €")
        col3.metric(":material/calendar_month: Jours enregistrés", len(donnees))
        col4.metric(":material/account_balance: Bénéfice estimé", f"{benefice:,.0f} €")
        col5.metric(":material/pie_chart: Marge estimée", f"{marge:.1f}%")
        if len(couts_connus) < len(donnees):
            st.caption(
                f"Rentabilité calculée sur {len(couts_connus)} jour(s) avec coûts renseignés "
                f"sur {len(donnees)}. Les coûts historiques inconnus ne sont pas assimilés à zéro."
            )

        alertes = hebdomadaire[hebdomadaire["Évolution (%)"] < -15]
        if not alertes.empty:
            st.warning(
                "Baisse supérieure à 15 % par rapport à la semaine précédente du même magasin et du même mois.",
                icon=":material/trending_down:",
            )
            st.dataframe(
                alertes[["Magasin", "Mois", "Annee", "Semaine", "Total semaine", "Évolution (%)"]],
                hide_index=True,
                width="stretch",
            )

        colA, colB = st.columns(2)
        with colA:
            fig = px.bar(
                hebdomadaire, x="Période", y="Total semaine", color="Magasin",
                title="Chiffre d’affaires par semaine", barmode="group",
                color_discrete_sequence=["#2563eb", "#14b8a6", "#f59e0b"],
            )
            st.plotly_chart(fig, width="stretch")
        with colB:
            ordre_jours = {jour: index for index, jour in enumerate(JOURS)}
            par_jour = (
                donnees.groupby("Jour", as_index=False, dropna=False)["Ventes"]
                .mean().rename(columns={"Ventes": "Moyenne des ventes"})
            )
            par_jour["Ordre"] = par_jour["Jour"].map(ordre_jours).fillna(99)
            par_jour = par_jour.sort_values(["Ordre", "Jour"]).drop(columns="Ordre")
            fig_jour = px.bar(
                par_jour, x="Jour", y="Moyenne des ventes",
                title="Ventes moyennes par jour", color="Moyenne des ventes",
                color_continuous_scale=["#bfdbfe", "#2563eb"],
            )
            st.plotly_chart(fig_jour, width="stretch")

        st.subheader("Résumé hebdomadaire")
        st.dataframe(
            hebdomadaire[["Magasin", "Mois", "Annee", "Semaine", "Total semaine", "Évolution (%)"]],
            hide_index=True,
            width="stretch",
        )
# ===================== AJOUTER VENTES =====================
elif page == "Saisie des ventes":
    st.title("Saisir les ventes")
    st.caption("Enregistrez les totaux journaliers ou détaillez les ventes par produit.")
    tab_jour, tab_produit = st.tabs(["Totaux journaliers", "Lignes par produit"])

    generation_magasin = st.session_state.get("generation_magasin", 0)
    with st.expander("Ajouter une boutique ou un magasin"):
        with st.form("formulaire_ajout_magasin", clear_on_submit=True):
            nouveau_magasin = st.text_input(
                "Nom de la boutique ou du magasin",
                key=f"nouveau_magasin_{utilisateur['id']}_{generation_magasin}",
            )
            ajouter_magasin = st.form_submit_button(
                "Ajouter le magasin", icon=":material/store:"
            )
        if ajouter_magasin:
            nom_magasin = nouveau_magasin.strip()
            if not nom_magasin:
                st.error("Le nom du magasin est obligatoire.")
            elif any(
                nom.casefold() == nom_magasin.casefold()
                for nom in lister_magasins()
            ):
                st.error("Ce magasin existe déjà.")
            else:
                st.session_state.magasins = pd.concat(
                    [
                        st.session_state.magasins,
                        pd.DataFrame([{"Magasin": nom_magasin}]),
                    ],
                    ignore_index=True,
                )
                sauvegarder_magasins(st.session_state.magasins)
                st.session_state.generation_magasin = generation_magasin + 1
                st.success(f"Magasin « {nom_magasin} » ajouté.")
                st.rerun()

    with tab_jour:
        generation_semaine = st.session_state.get("generation_saisie_semaine", 0)
        prefixe_semaine = f"{utilisateur['id']}_{generation_semaine}"
        with st.form("formulaire_totaux_journaliers", clear_on_submit=True):
            col_magasin, col_date = st.columns(2)
            with col_magasin:
                magasins_disponibles = lister_magasins()
                magasin = st.selectbox(
                    "Magasin",
                    magasins_disponibles,
                    key=f"hebdo_magasin_{prefixe_semaine}",
                )
            with col_date:
                lundi_defaut = date.today() - timedelta(days=date.today().weekday())
                lundi = st.date_input(
                    "Date de la semaine",
                    value=lundi_defaut,
                    key=f"hebdo_date_{prefixe_semaine}",
                    help="La date choisie sera automatiquement ramenée au lundi de sa semaine.",
                )
            debut_semaine = lundi - timedelta(days=lundi.weekday())
            fin_semaine = debut_semaine + timedelta(days=6)
            periode_iso = debut_semaine.isocalendar()
            st.caption(
                f"Semaine ISO S{periode_iso.week:02d} · {periode_iso.year} "
                f"— du {debut_semaine:%d/%m/%Y} au {fin_semaine:%d/%m/%Y}"
            )

            st.subheader("Chiffre d’affaires et coûts par jour")
            suivre_couts = st.checkbox(
                "Renseigner les coûts quotidiens pour estimer la rentabilité",
                key=f"saisie_suivre_couts_{prefixe_semaine}",
            )
            colonnes_jours = st.columns(4)
            ventes, couts = [], []
            for index, jour in enumerate(JOURS):
                date_jour = debut_semaine + timedelta(days=index)
                with colonnes_jours[index % 4]:
                    st.markdown(f"**{jour} · {date_jour:%d/%m/%Y}**")
                    ventes.append(st.number_input(
                        f"Ventes (€) · {jour}", min_value=0.0, value=0.0,
                        step=50.0, key=f"vente_jour_{prefixe_semaine}_{index}",
                    ))
                    couts.append(
                        st.number_input(
                            f"Coûts (€) · {jour}", min_value=0.0, value=0.0,
                            step=10.0, key=f"cout_jour_{prefixe_semaine}_{index}",
                        )
                        if suivre_couts
                        else None
                    )
            enregistrer_semaine = st.form_submit_button(
                "Enregistrer la semaine",
                type="primary",
                icon=":material/save:",
            )

        if enregistrer_semaine:
            dates_vente = [(debut_semaine + timedelta(days=index)).isoformat() for index in range(7)]
            deja_saisies = st.session_state.df[
                st.session_state.df["Magasin"].astype(str).eq(magasin.strip())
                & st.session_state.df["DateVente"].astype(str).isin(dates_vente)
            ]
            if not magasin.strip():
                st.error("Le nom du magasin est obligatoire.")
            elif not deja_saisies.empty:
                st.error("Une ou plusieurs journées de cette semaine existent déjà pour ce magasin. Modifiez-les dans Données.")
            else:
                dates_jour = [debut_semaine + timedelta(days=index) for index in range(7)]
                nouvelles = pd.DataFrame({
                    "Magasin": [magasin.strip()] * 7,
                    "Mois": [
                        f"{MOIS_FR[jour.month - 1]} {jour.year}" for jour in dates_jour
                    ],
                    "Semaine": [f"S{jour.isocalendar().week}" for jour in dates_jour],
                    "Annee": [jour.year for jour in dates_jour],
                    "Jour": JOURS,
                    "Ventes": ventes,
                    "Date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "DateVente": dates_vente,
                    "Cout": couts,
                    "Canal": [""] * 7,
                })
                st.session_state.df = pd.concat(
                    [st.session_state.df, nouvelles], ignore_index=True
                )
                sauvegarder_donnees(st.session_state.df)
                st.session_state.derniere_semaine_enregistree = {
                    "user_id": utilisateur["id"],
                    "magasin": magasin,
                    "semaine": periode_iso.week,
                    "annee_iso": periode_iso.year,
                    "debut": debut_semaine.isoformat(),
                    "fin": fin_semaine.isoformat(),
                    "lignes": nouvelles[
                        ["DateVente", "Jour", "Mois", "Semaine", "Annee", "Ventes"]
                    ].to_dict("records"),
                }
                st.session_state.confirmation_saisie_dashboard = {
                    "user_id": utilisateur["id"],
                    "message": (
                        f"Semaine ISO S{periode_iso.week:02d} · {periode_iso.year} "
                        f"enregistrée pour « {magasin} » "
                        f"(du {debut_semaine:%d/%m/%Y} au {fin_semaine:%d/%m/%Y})."
                    ),
                }
                st.session_state.generation_saisie_semaine = generation_semaine + 1
                st.session_state.page = "Tableau de bord"
                st.rerun()

        confirmation_semaine = st.session_state.get("derniere_semaine_enregistree")
        if confirmation_semaine and confirmation_semaine["user_id"] == utilisateur["id"]:
            debut_enregistre = date.fromisoformat(confirmation_semaine["debut"])
            fin_enregistree = date.fromisoformat(confirmation_semaine["fin"])
            st.success(
                f"Semaine ISO S{confirmation_semaine['semaine']:02d} · "
                f"{confirmation_semaine['annee_iso']} enregistrée pour "
                f"« {confirmation_semaine['magasin']} » "
                f"(du {debut_enregistre:%d/%m/%Y} au {fin_enregistree:%d/%m/%Y})."
            )
            st.dataframe(
                pd.DataFrame(confirmation_semaine["lignes"]),
                hide_index=True,
                width="stretch",
                column_config={
                    "DateVente": st.column_config.TextColumn("Date de vente"),
                    "Annee": st.column_config.NumberColumn("Année"),
                    "Ventes": st.column_config.NumberColumn("Ventes (€)", format="%.2f"),
                },
            )

    with tab_produit:
        catalogue = st.session_state.catalogue_produits
        magasins_connus = lister_magasins()
        generation_produit = st.session_state.get("generation_saisie_produit", 0)
        prefixe_produit = f"{utilisateur['id']}_{generation_produit}"
        with st.expander("Gérer le catalogue produits"):
            with st.form("ajouter_produit_catalogue"):
                nouveau_produit = st.text_input("Nom du produit")
                nouvelle_categorie = st.text_input("Catégorie", value="Général")
                ajouter_produit = st.form_submit_button("Ajouter au catalogue")
            if ajouter_produit:
                if not nouveau_produit.strip():
                    st.error("Le nom du produit est obligatoire.")
                elif catalogue["Produit"].astype(str).str.casefold().eq(
                    nouveau_produit.strip().casefold()
                ).any():
                    st.error("Ce produit existe déjà dans le catalogue.")
                else:
                    catalogue = pd.concat(
                        [catalogue, pd.DataFrame([{
                            "Produit": nouveau_produit.strip(),
                            "Categorie": nouvelle_categorie.strip() or "Général",
                        }])],
                        ignore_index=True,
                    )
                    st.session_state.catalogue_produits = catalogue
                    sauvegarder_catalogue(catalogue)
                    st.success("Produit ajouté au catalogue.")
                    st.rerun()

            if not catalogue.empty:
                st.caption("Produits enregistrés")
                catalogue_edite = st.data_editor(
                    catalogue,
                    hide_index=True,
                    width="stretch",

                    key="editeur_catalogue_produits",
                )
                if st.button("Enregistrer le catalogue", key="sauver_catalogue"):
                    catalogue_edite["Produit"] = catalogue_edite["Produit"].astype(str).str.strip()
                    catalogue_edite["Categorie"] = (
                        catalogue_edite["Categorie"].fillna("Général").astype(str).str.strip()
                    )
                    if catalogue_edite["Produit"].eq("").any():
                        st.error("Le nom de chaque produit est obligatoire.")
                    elif catalogue_edite["Produit"].str.casefold().duplicated().any():
                        st.error("Le catalogue ne peut pas contenir deux fois le même produit.")
                    else:
                        st.session_state.catalogue_produits = catalogue_edite.reset_index(drop=True)
                        sauvegarder_catalogue(st.session_state.catalogue_produits)
                        st.success("Catalogue mis à jour.")
                        st.rerun()

        if catalogue.empty:
            st.info("Ajoutez d’abord un produit au catalogue pour saisir une vente détaillée.")
        else:
            with st.form("saisie_ligne_produit", clear_on_submit=True):
                p1, p2, p3 = st.columns(3)
                with p1:
                    date_produit = st.date_input(
                        "Date de vente",
                        value=date.today(),
                        key=f"date_produit_{prefixe_produit}",
                    )
                    magasin_produit = st.selectbox(
                        "Magasin",
                        magasins_connus,
                        key=f"magasin_produit_{prefixe_produit}",
                    )
                with p2:
                    produit = st.selectbox(
                        "Produit",
                        catalogue["Produit"].astype(str).tolist(),
                        key=f"produit_{prefixe_produit}",
                    )
                    quantite = st.number_input(
                        "Quantité",
                        min_value=0.01,
                        value=1.0,
                        step=1.0,
                        key=f"quantite_{prefixe_produit}",
                    )
                with p3:
                    prix_unitaire = st.number_input(
                        "Prix unitaire (€)",
                        min_value=0.0,
                        value=0.0,
                        step=1.0,
                        key=f"prix_unitaire_{prefixe_produit}",
                    )
                    canal_selection = st.selectbox(
                        "Canal de vente",
                        ["Boutique", "E-commerce", "Téléphone", "Autre"],
                        key=f"canal_selection_{prefixe_produit}",
                    )
                canal = (
                    st.text_input(
                        "Précisez le canal",
                        key=f"canal_autre_{prefixe_produit}",
                    )
                    if canal_selection == "Autre"
                    else canal_selection
                )
                enregistrer_produit = st.form_submit_button("Enregistrer la vente produit")
            if enregistrer_produit:
                nouvelle_ligne = pd.DataFrame([{
                    "DateVente": date_produit.isoformat(),
                    "Magasin": magasin_produit,
                    "Produit": produit,
                    "Categorie": catalogue.loc[
                        catalogue["Produit"].astype(str).eq(produit), "Categorie"
                    ].iloc[0],
                    "Quantite": quantite,
                    "Prix unitaire": prix_unitaire,
                    "Canal": canal.strip(),
                    "Date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                }])
                st.session_state.ventes_produits = pd.concat(
                    [ventes_produits, nouvelle_ligne], ignore_index=True
                )
                sauvegarder_ventes_produits(st.session_state.ventes_produits)
                periode_produit = date_produit.isocalendar()
                st.session_state.derniere_vente_produit_enregistree = {
                    "user_id": utilisateur["id"],
                    "produit": produit,
                    "date": date_produit.isoformat(),
                    "mois": f"{MOIS_FR[date_produit.month - 1]} {date_produit.year}",
                    "semaine": periode_produit.week,
                    "annee_iso": periode_produit.year,
                }
                st.session_state.confirmation_saisie_dashboard = {
                    "user_id": utilisateur["id"],
                    "message": (
                        f"Vente de « {produit} » enregistrée le "
                        f"{date_produit:%d/%m/%Y} — {MOIS_FR[date_produit.month - 1]} "
                        f"{date_produit.year}, semaine ISO S{periode_produit.week:02d} "
                        f"· {periode_produit.year}."
                    ),
                }
                st.session_state.generation_saisie_produit = generation_produit + 1
                st.session_state.page = "Tableau de bord"
                st.rerun()
            confirmation_produit = st.session_state.get(
                "derniere_vente_produit_enregistree"
            )
            if (
                confirmation_produit
                and confirmation_produit["user_id"] == utilisateur["id"]
            ):
                st.success(
                    f"Vente de « {confirmation_produit['produit']} » enregistrée "
                    f"le {date.fromisoformat(confirmation_produit['date']):%d/%m/%Y}."
                )
                st.caption(
                    f"Période : {confirmation_produit['mois']} · "
                    f"Semaine ISO S{confirmation_produit['semaine']:02d} · "
                    f"{confirmation_produit['annee_iso']}."
                )

# ===================== GESTION SIMPLE DES DONNÉES =====================
elif page == "Données importées":
    st.title("Explorer les données importées")
    st.caption("Consultez et corrigez votre jeu de données avant d’analyser les résultats.")
    tab_totaux, tab_lignes = st.tabs(["Totaux journaliers", "Lignes par produit"])

    with tab_totaux:
        if st.session_state.df.empty:
            st.info("Aucun total journalier enregistré.")
        else:
            doublons_existants = detecter_doublons_journaliers(
                st.session_state.df
            )
            if not doublons_existants.empty:
                st.warning(
                    f"{len(doublons_existants)} ligne(s) semblent répétées "
                    "pour le même magasin, la même période et le même jour. "
                    "Vérifiez-les avant de les supprimer."
                )
                with st.expander("Examiner les doublons potentiels"):
                    st.dataframe(
                        doublons_existants[
                            ["Magasin", "Mois", "Annee", "Semaine", "Jour", "Ventes", "DateVente"]
                        ],
                        hide_index=True,
                        width="stretch",
                    )

            df_display = st.session_state.df.sort_values(
                by="Date", ascending=False
            ).reset_index(drop=True)
            df_display["DateVente"] = pd.to_datetime(
                df_display["DateVente"], errors="coerce"
            ).dt.date
            df_display.insert(0, "Supprimer", False)
            edited_df = st.data_editor(
                df_display,
                width="stretch",
                hide_index=True,
                column_config={
                    "Supprimer": st.column_config.CheckboxColumn("Sélectionner", width=100),
                    "Ventes": st.column_config.NumberColumn("Ventes (€)", format="%.2f"),
                    "Cout": st.column_config.NumberColumn("Coûts (€)", format="%.2f"),
                    "DateVente": st.column_config.DateColumn("Date de vente"),
                    "Annee": st.column_config.NumberColumn("Année"),
                    "Date": st.column_config.TextColumn("Date de saisie", disabled=True),
                },
                key="editor",
            )
            actions = st.columns(2)
            if actions[0].button("Supprimer la sélection", icon=":material/delete:", key="supprimer_totaux"):
                conservees = edited_df[~edited_df["Supprimer"]].drop(columns="Supprimer")
                st.session_state.df = conservees.reset_index(drop=True)
                sauvegarder_donnees(st.session_state.df)
                st.rerun()
            if actions[1].button("Enregistrer les modifications", type="primary", icon=":material/save:", key="enregistrer_totaux"):
                ventes_corrigees, invalides = normaliser_ventes(
                    edited_df.drop(columns="Supprimer")
                )
                if invalides or ventes_corrigees["Ventes"].isna().any():
                    st.error("Toutes les ventes doivent contenir un montant numérique.")
                else:
                    couts = pd.to_numeric(ventes_corrigees["Cout"], errors="coerce")
                    couts_invalides = ventes_corrigees["Cout"].notna() & couts.isna()
                    if couts_invalides.any() or (couts.dropna() < 0).any():
                        st.error("Les coûts doivent être des montants numériques positifs ou vides.")
                    else:
                        ventes_corrigees["Cout"] = couts
                        st.session_state.df = ventes_corrigees
                        sauvegarder_donnees(st.session_state.df)
                        st.success("Modifications enregistrées.")
                        st.rerun()

    with tab_lignes:
        if ventes_produits.empty:
            st.info("Aucune vente détaillée par produit.")
        else:
            lignes_editees = ventes_produits.copy()
            lignes_editees["DateVente"] = pd.to_datetime(
                lignes_editees["DateVente"], errors="coerce"
            ).dt.date
            lignes_editees.insert(0, "Supprimer", False)
            lignes_editees = st.data_editor(
                lignes_editees,
                width="stretch",
                hide_index=True,
                column_config={
                    "Supprimer": st.column_config.CheckboxColumn("Sélectionner", width=100),
                    "DateVente": st.column_config.DateColumn("Date de vente"),
                    "Quantite": st.column_config.NumberColumn("Quantité", min_value=0.01),
                    "Prix unitaire": st.column_config.NumberColumn("Prix unitaire (€)", min_value=0.0),
                    "Date": st.column_config.TextColumn("Date de saisie", disabled=True),
                },
                key="editor_produits",
            )
            actions = st.columns(2)
            if actions[0].button("Supprimer les lignes sélectionnées", icon=":material/delete:", key="supprimer_produits"):
                conservees = lignes_editees[~lignes_editees["Supprimer"]].drop(columns="Supprimer")
                st.session_state.ventes_produits = conservees.reset_index(drop=True)
                sauvegarder_ventes_produits(st.session_state.ventes_produits)
                st.rerun()
            if actions[1].button("Enregistrer les lignes", type="primary", icon=":material/save:", key="enregistrer_produits"):
                lignes_corrigees = lignes_editees.drop(columns="Supprimer")
                dates_lignes = pd.to_datetime(
                    lignes_corrigees["DateVente"], errors="coerce"
                )
                dates_lignes_invalides = dates_lignes.isna().any()
                lignes_corrigees["DateVente"] = dates_lignes.dt.strftime("%Y-%m-%d")
                for colonne in ["Quantite", "Prix unitaire"]:
                    lignes_corrigees[colonne] = pd.to_numeric(
                        lignes_corrigees[colonne], errors="coerce"
                    )
                if dates_lignes_invalides:
                    st.error("Chaque ligne doit avoir une date de vente valide.")
                elif lignes_corrigees[["Quantite", "Prix unitaire"]].isna().any().any():
                    st.error("Quantités et prix doivent être numériques.")
                elif (lignes_corrigees["Quantite"] <= 0).any() or (lignes_corrigees["Prix unitaire"] < 0).any():
                    st.error("La quantité doit être positive et le prix ne peut pas être négatif.")
                else:
                    st.session_state.ventes_produits = lignes_corrigees
                    sauvegarder_ventes_produits(lignes_corrigees)
                    st.success("Lignes détaillées enregistrées.")
                    st.rerun()

# ===================== ANALYSES (Version Améliorée) =====================
elif page == "Analyses":
    st.title("Analyses commerciales")
    st.caption("Comparez les performances et repérez les tendances.")
    filtres = st.columns(2)
    with filtres[0]:
        magasins_analyse = st.multiselect(
            "Magasins",
            sorted(journal["Magasin"].dropna().astype(str).unique()),
            default=sorted(journal["Magasin"].dropna().astype(str).unique()),
            key="analyse_magasins",
        )
    with filtres[1]:
        mois_analyse = st.multiselect(
            "Mois",
            sorted(journal["Mois"].dropna().astype(str).unique()),
            default=sorted(journal["Mois"].dropna().astype(str).unique()),
            key="analyse_mois",
        )
    debut_analyse, fin_analyse = ajouter_filtres_periode(journal, "analyse")
    analysees = journal[
        journal["Magasin"].astype(str).isin(magasins_analyse)
        & journal["Mois"].astype(str).isin(mois_analyse)
    ].copy()
    analysees = filtrer_periode(analysees, debut_analyse, fin_analyse)
    produits_analyses = ventes_produits[
        ventes_produits["Magasin"].astype(str).isin(magasins_analyse)
    ].copy()
    produits_analyses["DateVente"] = pd.to_datetime(
        produits_analyses["DateVente"], errors="coerce"
    ).dt.normalize()
    produits_analyses = filtrer_periode(
        produits_analyses, debut_analyse, fin_analyse
    )
    
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "Par semaine",
        "Par jour",
        "Par magasin",
        "Tendance",
        "Meilleures et faibles ventes",
        "Produits et canaux",
    ])
    
    with tab1:
        st.subheader("Résumé par Semaine")
        weekly = analysees.groupby(['Magasin', 'Mois', 'Semaine'])['Ventes'].agg(
            ['sum', 'mean', 'max', 'min', 'count']
        ).round(2)
        weekly = weekly.rename(columns={
            'sum': 'Total Semaine', 
            'mean': 'Moyenne/Jour', 
            'count': 'Jours'
        })
        st.dataframe(weekly, width='stretch')
        
        # Graphique Total par Semaine
        fig_week = px.bar(weekly.reset_index(), 
                         x='Semaine', 
                         y='Total Semaine',
                         color='Magasin',
                         title="Total des Ventes par Semaine")
        st.plotly_chart(fig_week, width='stretch')
    
    with tab2:
        st.subheader("Performance par Jour de la Semaine")
        by_day = analysees.groupby('Jour')['Ventes'].agg(['mean', 'sum', 'max', 'min']).round(2)
        by_day = by_day.rename(columns={'mean': 'Moyenne', 'sum': 'Total'})
        
        col_day1, col_day2 = st.columns(2)
        with col_day1:
            st.dataframe(by_day, width='stretch')
        with col_day2:
            fig_day = px.bar(by_day.reset_index(), 
                           x='Jour', 
                           y='Moyenne',
                           title="Moyenne des Ventes par Jour",
                           color='Moyenne')
            st.plotly_chart(fig_day, width='stretch')
    
    with tab3:
        st.subheader("Statistiques par Magasin")
        if len(analysees['Magasin'].unique()) > 1:
            magasin_stats = analysees.groupby('Magasin')['Ventes'].agg(
                ['sum', 'mean', 'max', 'min', 'count']
            ).round(2)
            magasin_stats = magasin_stats.rename(columns={
                'sum': 'Total Ventes', 
                'mean': 'Moyenne/Jour',
                'count': 'Jours'
            })
            st.dataframe(magasin_stats, width='stretch')
        else:
            st.info("Ajoute plusieurs magasins pour voir la comparaison")
    
    with tab4:
        st.subheader("Tendance et croissance")
        weekly_trend = analysees.groupby(['Mois', 'Semaine'])['Ventes'].sum().reset_index()
        weekly_trend['Croissance %'] = weekly_trend['Ventes'].pct_change() * 100
        
        st.dataframe(weekly_trend, width='stretch')
        
        fig_trend = px.line(weekly_trend, 
                           x=weekly_trend.index, 
                           y='Ventes', 
                           markers=True,
                           title="Évolution Globale des Ventes")
        st.plotly_chart(fig_trend, width='stretch')
        
        # Croissance
        fig_growth = px.bar(weekly_trend, 
                           x=weekly_trend.index, 
                           y='Croissance %',
                           title="Taux de Croissance (%)",
                           color='Croissance %',
                           color_continuous_scale=['red', 'lightgrey', 'green'])
        st.plotly_chart(fig_growth, width='stretch')
    
    with tab5:
        st.subheader("Meilleures et plus faibles journées")
        col_top, col_flop = st.columns(2)
        ventes_valides = analysees[analysees["Ventes"].notna()]
        
        with col_top:
            st.write("**Meilleures journées**")
            st.dataframe(ventes_valides.nlargest(10, 'Ventes')[['Magasin', 'Mois', 'Semaine', 'Jour', 'Ventes']], width='stretch')
        
        with col_flop:
            st.write("**Journées les plus faibles**")
            st.dataframe(ventes_valides.nsmallest(10, 'Ventes')[['Magasin', 'Mois', 'Semaine', 'Jour', 'Ventes']], width='stretch')

    with tab6:
        st.subheader("Performance par produit et canal")
        if produits_analyses.empty:
            st.info("Ajoutez des lignes de vente détaillées pour analyser les produits et les canaux.")
        else:
            produits_analyses["Chiffre d’affaires"] = (
                pd.to_numeric(produits_analyses["Quantite"], errors="coerce")
                * pd.to_numeric(produits_analyses["Prix unitaire"], errors="coerce")
            )
            par_produit = (
                produits_analyses.groupby(["Produit", "Categorie"], as_index=False)
                .agg(
                    Quantité=("Quantite", "sum"),
                    **{"Chiffre d’affaires": ("Chiffre d’affaires", "sum")},
                )
                .sort_values("Chiffre d’affaires", ascending=False)
            )
            par_canal = (
                produits_analyses.groupby("Canal", as_index=False)
                .agg(
                    Quantité=("Quantite", "sum"),
                    **{"Chiffre d’affaires": ("Chiffre d’affaires", "sum")},
                )
                .sort_values("Chiffre d’affaires", ascending=False)
            )
            col_produit, col_canal = st.columns(2)
            with col_produit:
                st.dataframe(par_produit, hide_index=True, width="stretch")
                st.plotly_chart(
                    px.bar(
                        par_produit,
                        x="Produit",
                        y="Chiffre d’affaires",
                        color="Categorie",
                        title="Chiffre d’affaires par produit",
                    ),
                    width="stretch",
                )
            with col_canal:
                st.dataframe(par_canal, hide_index=True, width="stretch")
                st.plotly_chart(
                    px.pie(
                        par_canal,
                        names="Canal",
                        values="Chiffre d’affaires",
                        title="Répartition par canal",
                    ),
                    width="stretch",
                )
# ===================== PRÉVISIONS (Version Améliorée & Corrigée) =====================
elif page == "Prévisions":
    st.title("Prévisions des ventes")
    
    if df.empty:
        st.warning("Aucune donnée disponible pour faire des prévisions.")
    else:
        # Calcul des données hebdomadaires
        weekly = df.groupby(['Mois', 'Semaine'])['Ventes'].sum().reset_index()
        weekly = weekly.sort_values(by=['Mois', 'Semaine']).reset_index(drop=True)
        
        # Métriques principales
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Moyenne Hebdomadaire", f"{weekly['Ventes'].mean():,.0f} €")
        with col2:
            st.metric("Dernière Semaine", f"{weekly['Ventes'].iloc[-1]:,} €")
        with col3:
            croissance_moy = weekly['Ventes'].pct_change().mean() * 100
            st.metric("Croissance Moyenne", f"{croissance_moy:.2f}%")
        
        st.subheader("Prévisions sur les six prochaines semaines")
        
        scenario = st.radio("Choisir un scénario de prévision :", 
                           ["Optimiste (+5%)", "Réaliste (+2.5%)", "Prudent (-1%)"],
                           horizontal=True)
        
        if scenario == "Optimiste (+5%)":
            taux = 0.05
        elif scenario == "Réaliste (+2.5%)":
            taux = 0.025
        else:
            taux = -0.01
        
        last_value = weekly['Ventes'].iloc[-1]
        predictions = []
        
        for i in range(1, 7):
            prev_value = last_value * (1 + taux) ** i
            predictions.append(round(prev_value))
        
        # Tableau des prévisions
        prev_df = pd.DataFrame({
            "Semaine": [f"Semaine +{i}" for i in range(1, 7)],
            "Prévision (€)": predictions
        })
        
        colA, colB = st.columns([3, 1])
        with colA:
            st.dataframe(prev_df, width='stretch', hide_index=True)
        with colB:
            total_prev = sum(predictions)
            st.metric("Total Prévu (6 semaines)", f"{total_prev:,} €")
        
        # Graphique Historique + Prévision
        import plotly.graph_objects as go   # Import local pour éviter les erreurs
        
        fig = go.Figure()
        
        # Historique
        fig.add_trace(go.Scatter(
            x=weekly.index,
            y=weekly['Ventes'],
            mode='lines+markers',
            name='Historique',
            line=dict(color='royalblue', width=3)
        ))
        
        # Prévisions
        fig.add_trace(go.Scatter(
            x=list(range(len(weekly), len(weekly) + 6)),
            y=predictions,
            mode='lines+markers',
            name='Prévision',
            line=dict(color='orange', width=3, dash='dash')
        ))
        
        fig.update_layout(
            title="Évolution Historique + Prévisions Futures",
            xaxis_title="Période (Semaines)",
            yaxis_title="Ventes (€)",
            height=550,
            legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01)
        )
        
        st.plotly_chart(fig, width='stretch')
        
        st.info("Le scénario réaliste constitue un point de départ pour la planification budgétaire.", icon=":material/lightbulb:")

# ===================== OBJECTIFS AVEC BARRES COLORÉES =====================
elif page == "Objectifs":
    st.title("Objectifs commerciaux")
    st.caption("Définissez une cible de chiffre d’affaires pour chaque magasin et chaque mois.")
    magasins_objectifs = sorted(journal["Magasin"].dropna().astype(str).unique())
    with st.form("formulaire_objectif"):
        col_magasin, col_mois, col_objectif = st.columns(3)
        magasin_objectif = col_magasin.text_input(
            "Magasin", magasins_objectifs[0] if magasins_objectifs else "Principal"
        )
        mois_objectif = col_mois.text_input(
            "Mois (ex. Novembre 2026)",
            f"{MOIS_FR[date.today().month - 1]} {date.today().year}",
        )
        montant_objectif = col_objectif.number_input(
            "Objectif mensuel (€)", min_value=1.0, value=10000.0, step=500.0
        )
        enregistrer_objectif = st.form_submit_button(
            "Enregistrer l’objectif", type="primary", icon=":material/flag:"
        )
    if enregistrer_objectif:
        if not magasin_objectif.strip() or not mois_objectif.strip():
            st.error("Le magasin et le mois sont obligatoires.")
        else:
            objectifs = st.session_state.objectifs.copy()
            cle = (
                objectifs["Magasin"].astype(str).str.casefold().eq(
                    magasin_objectif.strip().casefold()
                )
                & objectifs["Mois"].astype(str).str.casefold().eq(
                    mois_objectif.strip().casefold()
                )
            )
            objectifs = objectifs.loc[~cle]
            objectifs = pd.concat(
                [objectifs, pd.DataFrame([{
                    "Magasin": magasin_objectif.strip(),
                    "Mois": mois_objectif.strip(),
                    "Objectif": montant_objectif,
                }])],
                ignore_index=True,
            )
            st.session_state.objectifs = objectifs
            sauvegarder_objectifs(objectifs)
            st.success("Objectif enregistré.")
            st.rerun()

    objectifs = st.session_state.objectifs.copy()
    if objectifs.empty:
        st.info("Aucun objectif défini pour le moment.")
    else:
        st.subheader("Suivi des objectifs")
        realises = (
            journal.groupby(["Magasin", "Mois"], as_index=False)["Ventes"]
            .sum()
            .rename(columns={"Ventes": "Réalisé"})
        )
        suivi = objectifs.merge(realises, on=["Magasin", "Mois"], how="left")
        suivi["Réalisé"] = suivi["Réalisé"].fillna(0)
        suivi["Progression (%)"] = (suivi["Réalisé"] / suivi["Objectif"] * 100).round(1)
        st.dataframe(suivi, hide_index=True, width="stretch")
        for _, ligne in suivi.iterrows():
            progress = float(ligne["Progression (%)"])
            st.markdown(f"#### {ligne['Magasin']} · {ligne['Mois']}")
            st.progress(min(progress / 100, 1.0))
            st.caption(
                f"{ligne['Réalisé']:,.0f} € réalisés sur {ligne['Objectif']:,.0f} € "
                f"({progress:.1f} %)"
            )

        with st.expander("Modifier ou supprimer les objectifs"):
            edition = objectifs.copy()
            edition.insert(0, "Supprimer", False)
            edition = st.data_editor(
                edition,
                hide_index=True,
                width="stretch",
                column_config={
                    "Supprimer": st.column_config.CheckboxColumn("Supprimer"),
                    "Objectif": st.column_config.NumberColumn(
                        "Objectif mensuel (€)", min_value=1.0
                    ),
                },
                key="editeur_objectifs",
            )
            if st.button("Enregistrer les changements", key="sauver_objectifs"):
                edition = edition[~edition["Supprimer"]].drop(columns="Supprimer")
                edition["Objectif"] = pd.to_numeric(
                    edition["Objectif"], errors="coerce"
                )
                if edition[["Magasin", "Mois", "Objectif"]].isna().any().any() or (
                    edition["Objectif"] <= 0
                ).any():
                    st.error("Chaque objectif doit avoir un magasin, un mois et un montant positif.")
                else:
                    st.session_state.objectifs = edition.reset_index(drop=True)
                    sauvegarder_objectifs(st.session_state.objectifs)
                    st.success("Objectifs mis à jour.")
                    st.rerun()

# ===================== IMPORT / EXPORT =====================
elif page == "Import / Export":
    st.title("Import et export")
    st.caption(
        "Cette application analyse les ventes existantes; elle ne traite pas de commandes "
        "et ne remplace pas un logiciel de caisse."
    )
    tab_totaux, tab_produits, tab_export = st.tabs(
        ["Totaux journaliers", "Détail produits", "Téléchargements"]
    )

    def lire_fichier_charge(uploaded):
        try:
            if uploaded.name.lower().endswith(".csv"):
                return pd.read_csv(uploaded)
            return pd.read_excel(uploaded)
        except (pd.errors.ParserError, UnicodeDecodeError, ValueError, OSError) as erreur:
            st.error(f"Lecture du fichier impossible : {erreur}")
            return None

    with tab_totaux:
        st.caption(
            "Colonnes obligatoires : Magasin, Mois, Semaine, Jour, Ventes. "
            "DateVente et Cout sont facultatives."
        )
        fichier_totaux = st.file_uploader(
            "Fichier CSV ou Excel de ventes journalières",
            type=["csv", "xlsx"],
            key="import_totaux",
        )
        if fichier_totaux:
            import_brut = lire_fichier_charge(fichier_totaux)
            if import_brut is not None:
                import_net, erreurs, doublons = valider_import_journal(
                    import_brut, st.session_state.df
                )
                for erreur in erreurs:
                    st.error(erreur)
                if doublons:
                    st.warning(
                        f"{doublons} doublon(s) détecté(s) dans le fichier ou déjà présent(s). "
                        "Ils seront ignorés."
                    )
                st.write(f"{len(import_net)} ligne(s) prête(s) à importer.")
                st.dataframe(import_net.head(100), hide_index=True, width="stretch")
                if import_net.empty:
                    st.info("Aucune nouvelle ligne valide à fusionner.")
                elif not erreurs and st.button(
                    "Fusionner les ventes validées",
                    type="primary",
                    icon=":material/merge_type:",
                    key="fusion_totaux",
                ):
                    st.session_state.df = pd.concat(
                        [st.session_state.df, import_net], ignore_index=True
                    )
                    sauvegarder_donnees(st.session_state.df)
                    st.success(f"{len(import_net)} ligne(s) importée(s).")
                    st.rerun()

    with tab_produits:
        st.caption(
            "Colonnes obligatoires : DateVente, Magasin, Produit, Quantite, "
            "Prix unitaire et Canal. Categorie est facultative."
        )
        fichier_produits = st.file_uploader(
            "Fichier CSV ou Excel de lignes produits",
            type=["csv", "xlsx"],
            key="import_produits",
        )
        if fichier_produits:
            import_brut = lire_fichier_charge(fichier_produits)
            if import_brut is not None:
                import_net, erreurs, doublons = valider_import_produits(
                    import_brut, st.session_state.ventes_produits
                )
                for erreur in erreurs:
                    st.error(erreur)
                if doublons:
                    st.warning(f"{doublons} ligne(s) produit en doublon seront ignorées.")
                st.write(f"{len(import_net)} ligne(s) produit prête(s) à importer.")
                st.dataframe(import_net.head(100), hide_index=True, width="stretch")
                if import_net.empty:
                    st.info("Aucune nouvelle ligne produit valide à fusionner.")
                elif not erreurs and st.button(
                    "Fusionner les lignes produits validées",
                    type="primary",
                    icon=":material/merge_type:",
                    key="fusion_produits",
                ):
                    st.session_state.ventes_produits = pd.concat(
                        [st.session_state.ventes_produits, import_net],
                        ignore_index=True,
                    )
                    sauvegarder_ventes_produits(st.session_state.ventes_produits)
                    produits_catalogue = import_net[["Produit", "Categorie"]].drop_duplicates()
                    st.session_state.catalogue_produits = (
                        pd.concat(
                            [st.session_state.catalogue_produits, produits_catalogue],
                            ignore_index=True,
                        )
                        .drop_duplicates(subset=["Produit"], keep="last")
                        .reset_index(drop=True)
                    )
                    sauvegarder_catalogue(st.session_state.catalogue_produits)
                    st.success(f"{len(import_net)} ligne(s) produit importée(s).")
                    st.rerun()

    with tab_export:
        st.subheader("Télécharger les données")
        st.download_button(
            "Télécharger les totaux (CSV)",
            data=st.session_state.df.to_csv(index=False).encode("utf-8-sig"),
            file_name="ventes_journalieres.csv",
            mime="text/csv",
            icon=":material/download:",
        )
        st.download_button(
            "Télécharger les ventes produits (CSV)",
            data=st.session_state.ventes_produits.to_csv(index=False).encode("utf-8-sig"),
            file_name="ventes_produits.csv",
            mime="text/csv",
            icon=":material/download:",
        )

# ===================== PARAMÈTRES DU COMPTE =====================
elif page == "Paramètres":
    st.title("Paramètres du compte")
    st.caption("Gérez les paramètres de sécurité de votre compte Analyse PME.")

    mode_reinitialisation = st.session_state.get("mode_reinitialisation_mdp", False)
    if mode_reinitialisation:
        st.info("Choisissez un nouveau mot de passe pour terminer la réinitialisation.")
    else:
        st.markdown(f"Compte connecté : **{utilisateur['email']}**")

    with st.container(border=True):
        st.subheader("Sécurité")
        st.markdown("#### Modifier le mot de passe")
        with st.form("formulaire_modification_mot_de_passe"):
            if not mode_reinitialisation:
                mot_de_passe_actuel = st.text_input(
                    "Mot de passe actuel",
                    type="password",
                    key="mot_de_passe_actuel",
                )
            nouveau_mot_de_passe = st.text_input(
                "Nouveau mot de passe (8 caractères minimum)",
                type="password",
                key="nouveau_mot_de_passe",
            )
            confirmation_nouveau_mot_de_passe = st.text_input(
                "Confirmer le nouveau mot de passe",
                type="password",
                key="confirmation_nouveau_mot_de_passe",
            )
            modifier_mot_de_passe = st.form_submit_button(
                "Enregistrer le nouveau mot de passe",
                type="primary",
                icon=":material/lock_reset:",
            )

        if modifier_mot_de_passe:
            if not mode_reinitialisation and not mot_de_passe_actuel:
                st.error("Saisissez votre mot de passe actuel.")
            elif len(nouveau_mot_de_passe) < 8:
                st.error("Le nouveau mot de passe doit contenir au moins 8 caractères.")
            elif nouveau_mot_de_passe != confirmation_nouveau_mot_de_passe:
                st.error("Les deux nouveaux mots de passe ne correspondent pas.")
            elif not mode_reinitialisation and nouveau_mot_de_passe == mot_de_passe_actuel:
                st.error("Le nouveau mot de passe doit être différent de l’actuel.")
            else:
                attributs = {"password": nouveau_mot_de_passe}
                if not mode_reinitialisation:
                    attributs["current_password"] = mot_de_passe_actuel
                try:
                    resultat_modification = client.auth.update_user(attributs)
                except (AuthError, HTTPError) as erreur:
                    st.error(f"Modification du mot de passe impossible : {erreur}")
                else:
                    if resultat_modification.user is None:
                        st.error("Supabase n’a pas confirmé le changement de mot de passe.")
                    else:
                        st.session_state.pop("mode_reinitialisation_mdp", None)
                        st.session_state.pop("mot_de_passe_actuel", None)
                        st.session_state.pop("nouveau_mot_de_passe", None)
                        st.session_state.pop("confirmation_nouveau_mot_de_passe", None)
                        st.session_state.confirmation_securite = (
                            "Votre mot de passe a été modifié."
                        )
                        st.session_state.page = "Tableau de bord"
                        st.rerun()
