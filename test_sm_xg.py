import sys; sys.path.insert(0, '.')
from worldcup_predictor.providers.sportmonks_provider import SportmonksProvider
from worldcup_predictor.config.settings import get_settings

provider = SportmonksProvider(get_settings())

status, payload, err = provider.safe_get('fixtures/19606945', params={
    'include': 'statistics.type;xGFixture.type',
})

if payload:
    fixture = payload.get('data', {})
    
    # statistics
    stats = fixture.get('statistics', [])
    print(f'Statistics: {len(stats)}')
    types = set()
    for s in stats:
        t = s.get('type', {})
        if isinstance(t, dict):
            types.add(t.get('name', ''))
    print('Types:', sorted(types))
    
    # xG
    xg = fixture.get('xGFixture', [])
    print(f'xG entries: {len(xg) if isinstance(xg, list) else xg}')
    if xg and isinstance(xg, list):
        import json
        print('Sample xG:', json.dumps(xg[0], indent=2)[:300])
