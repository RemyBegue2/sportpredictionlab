from __future__ import annotations
from pathlib import Path
import json
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from sports_predictor.artifacts import verify_artifact_manifest
from sports_predictor.football import FootballPredictor
from sports_predictor.tennis import TennisPredictor

ROOT=Path(__file__).resolve().parent
st.set_page_config(page_title="Sports Prediction Lab V2.1", page_icon="⚽", layout="wide")
st.title("Sports Prediction Lab · V2")
st.caption("Probabilités auditables — football et tennis. Pas de résultat garanti.")

@st.cache_data
def load_data():
    f=pd.read_csv(ROOT/"data/real_snapshot/football_epl_2023_24_snapshot.csv")
    t=pd.read_csv(ROOT/"data/real_snapshot/tennis_atp_2025_snapshot.csv")
    return f,t

@st.cache_resource
def load_models():
    f=FootballPredictor(); t=TennisPredictor()
    artifact_dir=ROOT/"artifacts"
    fp=artifact_dir/"football_model.joblib"; tp=artifact_dir/"tennis_model.joblib"
    manifest=artifact_dir/"artifact_manifest.json"
    if fp.exists() and tp.exists() and manifest.exists():
        verify_artifact_manifest(artifact_dir,manifest)
        f.load(fp); t.load(tp)
    return f,t

football,tennis=load_data(); fmodel,tmodel=load_models()
metrics=json.loads((ROOT/"artifacts/metrics.json").read_text()) if (ROOT/"artifacts/metrics.json").exists() else {}

tab0,tab1,tab2,tab3,tab4=st.tabs(["Vue d'ensemble","Football","Tennis","Backtests","Données & audit"])
with tab0:
    c1,c2,c3,c4=st.columns(4)
    c1.metric("Matchs football embarqués",len(football)); c2.metric("Matchs tennis embarqués",len(tennis))
    c3.metric("Mode",metrics.get("mode","non entraîné")); c4.metric("Version","2.1")
    st.warning("Les métriques embarquées sont un smoke test sur un petit extrait réel. Elles ne doivent pas être interprétées comme une performance de production.")
    st.subheader("Chaîne de confiance")
    st.markdown("**Source → manifeste SHA-256 → normalisation → variables pré-match → split chronologique → calibration → backtest → interface.**")
    st.dataframe(pd.DataFrame([
        ["Data engineer","Provenance, schémas, cache, droits","Manifeste par fichier et adaptateurs explicites"],
        ["Statisticien sport","Baselines crédibles","Poisson–Dixon-Coles et Elo surface"],
        ["ML engineer","Fuite et surajustement","Calibration + garde-fou de mélange"],
        ["Auditeur risque","Promesses trompeuses","Probabilités, incertitude, avertissements"],
        ["Product designer","Compréhension","Pages séparées, explications et provenance"],
    ],columns=["Rôle","Retour","Décision intégrée"]),use_container_width=True,hide_index=True)

with tab1:
    st.header("Prédiction football 1N2")
    teams=sorted(set(football.home_team)|set(football.away_team))
    c1,c2,c3=st.columns(3)
    home=c1.selectbox("Équipe à domicile",teams,index=teams.index("Arsenal") if "Arsenal" in teams else 0)
    away_options=[x for x in teams if x!=home]; away=c2.selectbox("Équipe à l'extérieur",away_options)
    cutoff=pd.to_datetime(football.date,utc=True).max().date(); date=c3.date_input("Date du match",cutoff+pd.Timedelta(days=7),min_value=cutoff+pd.Timedelta(days=1))
    if st.button("Calculer les probabilités football",type="primary"):
        if fmodel.artifacts is None: st.error("Entraînez d'abord le modèle : python scripts/train_snapshot.py")
        else:
            fixture=pd.DataFrame([{"date":str(date),"league":"E0","home_team":home,"away_team":away}])
            pred=fmodel.predict_matches(football,fixture)[0]
            probs=[pred["home_win"],pred["draw"],pred["away_win"]]
            cols=st.columns(3)
            for col,label,p in zip(cols,[home,"Nul",away],probs): col.metric(label,f"{p:.1%}")
            fig=go.Figure(go.Bar(x=[home,"Nul",away],y=probs,text=[f"{x:.1%}" for x in probs],textposition="auto"))
            fig.update_yaxes(range=[0,1],tickformat=".0%",title="Probabilité")
            st.plotly_chart(fig,use_container_width=True)
            st.write("Buts attendus :",round(pred["expected_home_goals"],2),"–",round(pred["expected_away_goals"],2))
            st.dataframe(pd.DataFrame(pred["top_scores"]),use_container_width=True,hide_index=True)

with tab2:
    st.header("Prédiction tennis · Elo non calibré sur le snapshot")
    players=sorted(set(tennis.winner_name)|set(tennis.loser_name)); c1,c2,c3=st.columns(3)
    p1=c1.selectbox("Joueur 1",players,index=players.index("Taylor Fritz") if "Taylor Fritz" in players else 0)
    p2=c2.selectbox("Joueur 2",[x for x in players if x!=p1])
    surface=c3.selectbox("Surface",["hard","clay","grass","carpet"])
    if st.button("Calculer les probabilités tennis",type="primary"):
        if tmodel.artifacts is None: st.error("Entraînez d'abord le modèle : python scripts/train_snapshot.py")
        else:
            fixture=pd.DataFrame([{"date":str(pd.Timestamp(tennis.date.max())+pd.Timedelta(days=7)),"tour":"ATP","surface":surface,"tournament_level":"A","best_of":3,"player_1":p1,"player_2":p2}])
            p=float(tmodel.predict_matches(tennis,fixture)[0]); c1,c2=st.columns(2); c1.metric(p1,f"{p:.1%}"); c2.metric(p2,f"{1-p:.1%}")
            st.progress(p,text=f"Probabilité estimée que {p1} gagne")
            st.caption("Le snapshot tennis ne contient que deux dates de tournoi : l’interface sert un Elo symétrique non calibré, sans revendication de performance.")

with tab3:
    st.header("Métriques et protocole")
    if metrics:
        st.json(metrics,expanded=False)
        rows=[]
        for sport in ["football","tennis"]:
            for k,v in metrics.get(sport,{}).items():
                if isinstance(v,(int,float)): rows.append({"sport":sport,"métrique":k,"valeur":v})
        if rows: st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
    st.markdown("""
    **Règle de promotion production** : aucun modèle n'est promu sur l'accuracy seule. Il doit battre la baseline sur log-loss, Brier/calibration, plusieurs fenêtres temporelles et sans fuite de données. Pour le football, la cote de marché dévigée est un benchmark séparé.
    """)

with tab4:
    st.header("Données, provenance et audit")
    provenance=json.loads((ROOT/"data/real_snapshot/PROVENANCE.json").read_text())
    st.json(provenance)
    st.markdown("""
    - Les variables de score et statistiques du match courant ne sont jamais disponibles avant le match.
    - Les statistiques post-match de tennis sont conservées uniquement pour fabriquer des agrégats **décalés** dans une future itération.
    - Les modèles joblib/pickle ne doivent être chargés que depuis une source de confiance.
    - Les conditions de licence du jeu ATP limitent le déploiement commercial sans autorisation.
    """)
    st.code("python scripts/download_real_data.py\npython scripts/train_real.py\nstreamlit run app.py",language="bash")
