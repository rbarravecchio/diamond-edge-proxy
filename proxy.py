"""
Diamond Edge Proxy Server v2
Uses pybaseball to fetch Statcast data — bypasses Baseball Savant blocking
"""
 
from flask import Flask, jsonify, request
from flask_cors import CORS
import os
from datetime import datetime, date
 
app = Flask(__name__)
CORS(app)
 
_cache = {}
_cache_time = {}
CACHE_TTL = 3600  # 1 hour cache
 
def is_cache_valid(key):
    if key not in _cache_time:
        return False
    return (datetime.now() - _cache_time[key]).seconds < CACHE_TTL
 
@app.route('/statcast')
def statcast():
    try:
        year = int(request.args.get('year', datetime.now().year))
        stat_type = request.args.get('type', 'pitcher')
        cache_key = f'statcast_{stat_type}_{year}'
 
        if is_cache_valid(cache_key):
            cached = _cache[cache_key].copy()
            cached['cached'] = True
            return jsonify(cached)
 
        from pybaseball import pitching_stats, batting_stats
 
        if stat_type == 'pitcher':
            df = pitching_stats(year, year, qual=1)
            if df is None or df.empty:
                return jsonify({'success': False, 'error': 'No pitcher data'}), 500
 
            pitchers = {}
            for _, row in df.iterrows():
                name = str(row.get('Name', ''))
                fgid = str(int(row.get('IDfg', 0)) if row.get('IDfg') else 0)
                pitchers[fgid] = {
                    'name':    name,
                    'xERA':    _f(row.get('xERA')),
                    'barrel':  _f(row.get('Barrel%')),
                    'hardHit': _f(row.get('HardHit%')),
                    'kPct':    _f(row.get('K%')),
                    'bbPct':   _f(row.get('BB%')),
                    'whiff':   _f(row.get('SwStr%')),
                    'era':     _f(row.get('ERA')),
                    'fip':     _f(row.get('FIP')),
                    'ip':      _f(row.get('IP')),
                    'team':    str(row.get('Team', '')),
                    'pa':      _i(row.get('TBF')),
                }
 
            result = {'success': True, 'year': year, 'type': stat_type,
                      'count': len(pitchers), 'pitchers': pitchers, 'cached': False}
            _cache[cache_key] = result
            _cache_time[cache_key] = datetime.now()
            return jsonify(result)
 
        else:
            df = batting_stats(year, year, qual=1)
            if df is None or df.empty:
                return jsonify({'success': False, 'error': 'No batter data'}), 500
 
            teams = {}
            for _, row in df.iterrows():
                team = str(row.get('Team', ''))
                if not team or team == 'nan': continue
                if team not in teams:
                    teams[team] = {'barrel':[], 'hardHit':[], 'kPct':[], 'bbPct':[], 'whiff':[]}
                for k, col in [('barrel','Barrel%'),('hardHit','HardHit%'),('kPct','K%'),('bbPct','BB%'),('whiff','SwStr%')]:
                    v = _f(row.get(col))
                    if v is not None: teams[team][k].append(v)
 
            result_teams = {t: {k: round(sum(v)/len(v),3) if v else None for k,v in m.items()} for t,m in teams.items()}
            result = {'success': True, 'year': year, 'type': 'team_batting',
                      'teams': result_teams, 'cached': False}
            _cache[cache_key] = result
            _cache_time[cache_key] = datetime.now()
            return jsonify(result)
 
    except ImportError:
        return jsonify({'success': False, 'error': 'pybaseball not installed — check requirements.txt'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
 
 
@app.route('/statcast/team')
def statcast_team():
    year = request.args.get('year', str(datetime.now().year))
    cache_key = f'statcast_batter_{year}'
    if is_cache_valid(cache_key):
        cached = _cache[cache_key].copy()
        cached['cached'] = True
        return jsonify(cached)
    from flask import request as req
    with app.test_request_context(f'/statcast?year={year}&type=batter'):
        return statcast()
 
 
@app.route('/umpire')
def umpire():
    try:
        date_str = request.args.get('date', date.today().strftime('%Y-%m-%d'))
        cache_key = f'umpire_{date_str}'
        if is_cache_valid(cache_key):
            return jsonify(_cache[cache_key])
 
        import requests as req
        headers = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}
        resp = req.get(f'https://umpscorecards.com/api/v1/umpires/games?date={date_str}', headers=headers, timeout=10)
        if resp.status_code == 404:
            return jsonify({'success': True, 'games': [], 'note': 'No umpire data yet'})
        resp.raise_for_status()
        data = resp.json()
        games = [{'homeTeam': g.get('homeTeam',''), 'awayTeam': g.get('awayTeam',''),
                  'umpire': g.get('umpire','Unknown'), 'favor': _f(g.get('favor')),
                  'runsImpact': _f(g.get('run_expectancy_impact') or g.get('re24')),
                  'accuracy': _f(g.get('accuracy'))} for g in (data if isinstance(data, list) else [])]
        result = {'success': True, 'date': date_str, 'games': games}
        _cache[cache_key] = result
        _cache_time[cache_key] = datetime.now()
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'games': []}), 500
 
 
@app.route('/')
def health():
    return jsonify({'status': 'Diamond Edge Proxy v2 — Online',
                    'endpoints': ['/statcast', '/statcast/team', '/umpire'],
                    'version': '2.0.0', 'cache': list(_cache.keys())})
 
 
def _f(val):
    try:
        return None if val is None or str(val)=='nan' else float(val)
    except: return None
 
def _i(val):
    try:
        return None if val is None or str(val)=='nan' else int(val)
    except: return None
 
 
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
 
from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
import os
 
app = Flask(__name__)
CORS(app)  # Allow all origins — Netlify needs this
 
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
}
 
# ─────────────────────────────────────────
#  STATCAST — Baseball Savant
# ─────────────────────────────────────────
@app.route('/statcast')
def statcast():
    try:
        year = request.args.get('year', '2026')
        min_pa = request.args.get('min', '20')
        stat_type = request.args.get('type', 'pitcher')  # pitcher or batter
 
        url = (
            f"https://baseballsavant.mlb.com/leaderboard/custom"
            f"?year={year}&type={stat_type}&filter=&sort=xera&sortDir=asc"
            f"&min={min_pa}"
            f"&selections=xba,xslg,xwoba,xera,exit_velocity_avg,"
            f"barrel_batted_rate,hard_hit_percent,k_percent,bb_percent,"
            f"whiff_percent,sprint_speed,p_formatted_speed"
            f"&limit=600"
        )
 
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
 
        pitchers = {}
        leaderboard = data.get('leaderboard', [])
        for row in leaderboard:
            # Pitchers use pitcher_id, batters use batter_id or player_id
            pid = str(
                row.get('pitcher_id') or
                row.get('batter_id') or
                row.get('player_id') or ''
            )
            if not pid:
                continue
            pitchers[pid] = {
                'xERA':     _f(row.get('xera')),
                'xBA':      _f(row.get('xba')),
                'xSLG':     _f(row.get('xslg')),
                'xwOBA':    _f(row.get('xwoba')),
                'exitVelo': _f(row.get('exit_velocity_avg')),
                'barrel':   _f(row.get('barrel_batted_rate')),
                'hardHit':  _f(row.get('hard_hit_percent')),
                'kPct':     _f(row.get('k_percent')),
                'bbPct':    _f(row.get('bb_percent')),
                'whiff':    _f(row.get('whiff_percent')),
                'name':     row.get('player_name', ''),
                'pa':       _i(row.get('pa') or row.get('abs')),
                'team':     row.get('team_name', ''),
            }
 
        return jsonify({
            'success': True,
            'year': year,
            'type': stat_type,
            'count': len(pitchers),
            'pitchers': pitchers,
        })
 
    except requests.exceptions.Timeout:
        return jsonify({'success': False, 'error': 'Baseball Savant timeout'}), 504
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
 
 
# ─────────────────────────────────────────
#  TEAM STATCAST — aggregated by team
# ─────────────────────────────────────────
@app.route('/statcast/team')
def statcast_team():
    """Aggregate batter Statcast by team for offensive dashboard"""
    try:
        year = request.args.get('year', '2026')
 
        url = (
            f"https://baseballsavant.mlb.com/leaderboard/custom"
            f"?year={year}&type=batter&filter=&sort=xwoba&sortDir=desc"
            f"&min=10"
            f"&selections=xba,xslg,xwoba,exit_velocity_avg,"
            f"barrel_batted_rate,hard_hit_percent,k_percent,bb_percent,"
            f"whiff_percent"
            f"&limit=1000"
        )
 
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
 
        # Aggregate by team
        teams = {}
        for row in data.get('leaderboard', []):
            team = row.get('team_name', '')
            if not team:
                continue
            if team not in teams:
                teams[team] = {
                    'xwOBA': [], 'barrel': [], 'hardHit': [],
                    'exitVelo': [], 'kPct': [], 'bbPct': [],
                    'whiff': [], 'xBA': []
                }
            def _add(key, val):
                v = _f(val)
                if v is not None:
                    teams[team][key].append(v)
 
            _add('xwOBA',   row.get('xwoba'))
            _add('barrel',  row.get('barrel_batted_rate'))
            _add('hardHit', row.get('hard_hit_percent'))
            _add('exitVelo',row.get('exit_velocity_avg'))
            _add('kPct',    row.get('k_percent'))
            _add('bbPct',   row.get('bb_percent'))
            _add('whiff',   row.get('whiff_percent'))
            _add('xBA',     row.get('xba'))
 
        # Average each metric per team
        result = {}
        for team, metrics in teams.items():
            result[team] = {
                k: round(sum(v)/len(v), 3) if v else None
                for k, v in metrics.items()
            }
 
        return jsonify({
            'success': True,
            'year': year,
            'teams': result,
        })
 
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
 
 
# ─────────────────────────────────────────
#  UMPIRE DATA — UmpScorecards
# ─────────────────────────────────────────
@app.route('/umpire')
def umpire():
    try:
        date = request.args.get('date', '')
        if not date:
            from datetime import date as dt
            date = dt.today().strftime('%Y-%m-%d')
 
        url = f"https://umpscorecards.com/api/v1/umpires/games?date={date}"
        resp = requests.get(url, headers=HEADERS, timeout=10)
 
        if resp.status_code == 404:
            return jsonify({'success': True, 'games': [], 'note': 'No umpire data for this date yet'})
 
        resp.raise_for_status()
        data = resp.json()
 
        # Normalize umpire data
        games = []
        for game in (data if isinstance(data, list) else []):
            games.append({
                'homeTeam':   game.get('homeTeam') or game.get('home_team', ''),
                'awayTeam':   game.get('awayTeam') or game.get('away_team', ''),
                'umpire':     game.get('umpire') or game.get('hp_umpire', 'Unknown'),
                'favor':      _f(game.get('favor')),
                'runsImpact': _f(game.get('run_expectancy_impact') or game.get('re24')),
                'accuracy':   _f(game.get('accuracy')),
                'missedCalls':_i(game.get('missed_calls')),
                'totalCalls': _i(game.get('total_calls')),
            })
 
        return jsonify({'success': True, 'date': date, 'games': games})
 
    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'games': []}), 500
 
 
# ─────────────────────────────────────────
#  HEALTH CHECK
# ─────────────────────────────────────────
@app.route('/')
def health():
    return jsonify({
        'status': 'Diamond Edge Proxy — Online',
        'endpoints': ['/statcast', '/umpire'],
        'version': '1.0.0',
    })
 
 
# ─────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────
def _f(val):
    try: return float(val) if val is not None else None
    except: return None
 
def _i(val):
    try: return int(val) if val is not None else None
    except: return None
 
 
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
 
