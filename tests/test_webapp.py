from fastapi.testclient import TestClient
from webapp import app

client = TestClient(app)

def test_health_and_home():
    assert client.get('/').status_code == 200
    health = client.get('/api/health')
    assert health.status_code == 200
    assert health.json()['status'] == 'ok'
    assert 'the_odds_api_configured' in health.json()

def test_prediction_endpoints():
    f = client.post('/api/football/predict', json={'home_team':'Arsenal','away_team':'Man City'})
    assert f.status_code == 200, f.text
    p = f.json()['probabilities']
    assert abs(sum(p.values()) - 1.0) < 1e-8
    t = client.post('/api/tennis/predict', json={'player_1':'Taylor Fritz','player_2':'Alexander Zverev','surface':'hard'})
    assert t.status_code == 200, t.text
    p2 = t.json()['probabilities']
    assert abs(sum(p2.values()) - 1.0) < 1e-8

def test_readiness_and_prediction_history():
    ready = client.get('/api/ready')
    assert ready.status_code == 200, ready.text
    before = client.get('/api/history/predictions?limit=200').json()['database']['predictions']
    response = client.post('/api/football/predict', json={'home_team':'Arsenal','away_team':'Chelsea'})
    assert response.status_code == 200, response.text
    assert response.json()['prediction_id'] > 0
    history = client.get('/api/history/predictions?limit=5')
    assert history.status_code == 200
    assert history.json()['database']['predictions'] >= before + 1
    assert history.json()['predictions'][0]['sport'] == 'football'

def test_daily_slate_uses_persisted_predictions_and_expires_stale_odds():
    from sports_predictor.database import record_prediction

    record_prediction(
        sport='football',
        model_version='3.1.0-test',
        fixture={'date':'2030-01-01','league':'E0','home_team':'Arsenal','away_team':'Chelsea'},
        probabilities={'home':0.5,'draw':0.25,'away':0.25},
        market_analysis={
            'observed_at':'2020-01-01T00:00:00Z',
            'market_type':'1N2',
            'shortlist':[{'selection':'Arsenal'}],
            'selections':[{'selection':'Arsenal','reasons':[]}],
            'warning':'research only',
        },
        decision='candidat recherche',
        provider_event_id='stale-event-test',
    )
    response = client.get('/api/bets/today?date=2030-01-01')
    assert response.status_code == 200
    payload = response.json()
    assert payload['source'] == 'postgresql'
    assert payload['summary']['research_candidates'] == 0
    assert payload['events'][0]['decision'] == 'à actualiser'
