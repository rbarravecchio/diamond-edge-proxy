"""
Diamond Edge Proxy Server v3
Uses FanGraphs API directly — more reliable than pybaseball
"""
from flask import Flask, jsonify, request
from flask_cors import CORS
import requests as req
import os
from datetime import datetime, date

app = Flask(__name__)
CORS(app)

_cache = {}
_cache_time = {}
CACHE_TTL = 3600

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Referer': 'https://www.fangraphs.com/',
}

def cache_valid(key):
    return key in _cache_time and (datetime.now() - _cache_time[key]).seconds < CACHE_TTL

def cache_set(key, val):
    _cache[key] = val
    _cache_time[key] = datetime.now()

@app.route('/')
def health():
    return jsonify({'status': 'Diamond Edge Proxy v3 — Online', 'version': '3.0.0',
                    'endpoints': ['/statcast', '/statcast/team', '/umpire'],
                    'cache': list(_cache.keys())})

@app.route('/statcast')
def statcast():
    year = request.args.get('year', str(datetime.now().year))
    stat_type = request.args.get('type', 'pitcher')
    cache_key = f'fg_{stat_type}_{year}'

    if cache_valid(cache_key):
        return jsonify({**_cache[cache_key], 'cached': True})

    try:
        # FanGraphs leaderboard API
        if stat_type == 'pitcher':
            url = (f'https://www.fangraphs.com/api/leaders/major-league/data'
                   f'?age=0&pos=all&stats=pit&lg=all&qual=1&season={year}'
                   f'&season1={year}&ind=0&team=0&rost=0&players=0'
                   f'&type=36&sortcol=7&sortdir=default&pagenum=1&pageitems=500')
        else:
            url = (f'https://www.fangraphs.com/api/leaders/major-league/data'
                   f'?age=0&pos=all&stats=bat&lg=all&qual=1&season={year}'
                   f'&season1={year}&ind=0&team=0&rost=0&players=0'
                   f'&type=23&sortcol=6&sortdir=default&pagenum=1&pageitems=600')

        resp = req.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json()

        rows = data.get('data', [])
        if not rows:
            return jsonify({'success': False, 'error': 'No data from FanGraphs', 'rows': 0}), 500

        pitchers = {}
        for row in rows:
            # FanGraphs uses playerid
            pid = str(row.get('playerid') or row.get('PlayerId') or '')
            name = str(row.get('PlayerName') or row.get('Name') or '')
            team = str(row.get('Team') or '')
            if not pid: continue

            if stat_type == 'pitcher':
                pitchers[pid] = {
                    'name':    name,
                    'team':    team,
                    'xERA':    _f(row.get('xERA')),
                    'barrel':  _f(row.get('Barrel%')),
                    'hardHit': _f(row.get('HardHit%')),
                    'kPct':    _f(row.get('K%')),
                    'bbPct':   _f(row.get('BB%')),
                    'whiff':   _f(row.get('SwStr%')),
                    'era':     _f(row.get('ERA')),
                    'fip':     _f(row.get('FIP')),
                    'ip':      _f(row.get('IP')),
                    'pa':      _i(row.get('TBF')),
                }
            else:
                pitchers[pid] = {
                    'name':    name,
                    'team':    team,
                    'barrel':  _f(row.get('Barrel%')),
                    'hardHit': _f(row.get('HardHit%')),
                    'kPct':    _f(row.get('K%')),
                    'bbPct':   _f(row.get('BB%')),
                    'whiff':   _f(row.get('SwStr%')),
                    'xwOBA':   _f(row.get('xwOBA')),
                    'pa':      _i(row.get('PA')),
                }

        result = {'success': True, 'year': year, 'type': stat_type,
                  'count': len(pitchers), 'pitchers': pitchers, 'cached': False}
        cache_set(cache_key, result)
        return jsonify(result)

    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'url': url if 'url' in dir() else ''}), 500


@app.route('/statcast/team')
def statcast_team():
    year = request.args.get('year', str(datetime.now().year))
    cache_key = f'fg_team_{year}'

    if cache_valid(cache_key):
        return jsonify({**_cache[cache_key], 'cached': True})

    try:
        url = (f'https://www.fangraphs.com/api/leaders/major-league/data'
               f'?age=0&pos=all&stats=bat&lg=all&qual=1&season={year}'
               f'&season1={year}&ind=0&team=0&rost=0&players=0'
               f'&type=23&sortcol=6&sortdir=default&pagenum=1&pageitems=1000')

        resp = req.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        rows = resp.json().get('data', [])

        teams = {}
        for row in rows:
            team = str(row.get('Team') or '')
            if not team or team in ('', 'nan'): continue
            if team not in teams:
                teams[team] = {'barrel':[],'hardHit':[],'kPct':[],'bbPct':[],'whiff':[],'xwOBA':[]}
            for k, col in [('barrel','Barrel%'),('hardHit','HardHit%'),('kPct','K%'),
                           ('bbPct','BB%'),('whiff','SwStr%'),('xwOBA','xwOBA')]:
                v = _f(row.get(col))
                if v is not None: teams[team][k].append(v)

        result_teams = {t:{k:round(sum(v)/len(v),3) if v else None for k,v in m.items()}
                        for t,m in teams.items()}
        result = {'success': True, 'year': year, 'teams': result_teams, 'cached': False}
        cache_set(cache_key, result)
        return jsonify(result)

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/umpire')
def umpire():
    try:
        date_str = request.args.get('date', date.today().strftime('%Y-%m-%d'))
        cache_key = f'ump_{date_str}'
        if cache_valid(cache_key):
            return jsonify(_cache[cache_key])

        headers = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}
        resp = req.get(f'https://umpscorecards.com/api/v1/umpires/games?date={date_str}',
                       headers=headers, timeout=10)
        if resp.status_code == 404:
            return jsonify({'success': True, 'games': [], 'note': 'No umpire data yet'})
        resp.raise_for_status()
        data = resp.json()
        games = [{'homeTeam': g.get('homeTeam',''), 'awayTeam': g.get('awayTeam',''),
                  'umpire': g.get('umpire','Unknown'),
                  'favor': _f(g.get('favor')),
                  'runsImpact': _f(g.get('run_expectancy_impact') or g.get('re24')),
                  'accuracy': _f(g.get('accuracy'))}
                 for g in (data if isinstance(data, list) else [])]
        result = {'success': True, 'date': date_str, 'games': games}
        cache_set(cache_key, result)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'games': []}), 500


def _f(val):
    try: return None if val is None or str(val) in ('nan','None','') else float(val)
    except: return None

def _i(val):
    try: return None if val is None or str(val) in ('nan','None','') else int(float(val))
    except: return None


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
