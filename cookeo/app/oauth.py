import base64,hmac,json,re,time,urllib.parse
SF_BASE='https://account.groupeseb.com'
REDIRECT='gsmoduser://tokens'
SF_CLIENT_ID=''
def authorize_url(state, nonce, market='CZ', lang='cs', client_id=SF_CLIENT_ID, brand='tefal'):
    if brand not in ('tefal', 'moulinex'):
        raise ValueError('Nepodporovaná značka přihlášení.')
    if not market.isascii() or not market.isalpha() or len(market) != 2:
        raise ValueError('Země musí být dvoupísmenný kód.')
    if not re.fullmatch(r'[a-z]{2}(?:[A-Z]{2})?',lang):
        raise ValueError('Neplatný RCU jazyk přihlášení.')
    rcu_lang=lang
    expid = f'expid_{brand}000{market.upper()}000{rcu_lang}000true'
    params = dict(client_id=client_id, redirect_uri=REDIRECT, response_type='token id_token refresh_token', state=state, nonce=nonce)
    return SF_BASE + '/services/oauth2/authorize/' + expid + '?' + urllib.parse.urlencode(params)

def normalize_redirect(raw):
    """Accept a URI or a browser console line, never a normal web page URL."""
    if not isinstance(raw, str) or len(raw) > 64000:
        raise ValueError('Neplatná délka návratového odkazu.')
    matches = re.findall('gsmoduser://tokens(?:/)?#[^\\s\\"\'<>]+', raw)
    if len(matches) != 1:
        raise ValueError('Vložený text neobsahuje jediný návratový odkaz gsmoduser://tokens#. Adresa https:// přihlašovací stránky nestačí.')
    return matches[0]

def accept_redirect(url, state, nonce, client_id=SF_CLIENT_ID, brand='tefal'):
    if brand not in ('tefal', 'moulinex'):
        raise ValueError('Nepodporovaná značka přihlášení.')
    url = normalize_redirect(url)
    if len(url) > 64000:
        raise ValueError('Neplatná délka návratového odkazu.')
    parsed = urllib.parse.urlsplit(url.strip())
    if parsed.scheme != 'gsmoduser' or parsed.netloc != 'tokens' or parsed.path not in ('', '/') or parsed.query:
        raise ValueError('Nesprávný návratový odkaz.')
    pairs = urllib.parse.parse_qsl(parsed.fragment, keep_blank_values=True)
    if len({k for k, v in pairs}) != len(pairs):
        raise ValueError('Duplicitní OAuth pole.')
    fields = dict(pairs)
    if not hmac.compare_digest(fields.get('state', ''), state):
        raise ValueError('Neshodný OAuth state.')
    if fields.get('error'):
        raise ValueError('Přihlášení výrobce odmítl.')
    if not all((fields.get(k) for k in ('id_token', 'access_token', 'refresh_token'))):
        raise ValueError('Přihlášení neposkytlo všechny potřebné tokeny.')
    try:
        payload = fields['id_token'].split('.')[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
    except (ValueError, IndexError, TypeError):
        raise ValueError('Neplatný formát ID tokenu.') from None
    if not hmac.compare_digest(str(claims.get('nonce', '')), nonce):
        raise ValueError('Neshodný OAuth nonce.')
    audiences = claims.get('aud', [])
    if isinstance(audiences, str):
        audiences = [audiences]
    if client_id not in audiences:
        raise ValueError('ID token patří jinému klientu.')
    if str(claims.get('iss', '')).rstrip('/') not in ('https://account.groupeseb.com', 'account.groupeseb.com'):
        raise ValueError('Neočekávaný vydavatel ID tokenu.')
    if not isinstance(claims.get('exp'), (int, float)) or claims['exp'] <= time.time():
        raise ValueError('ID token již vypršel.')
    return dict(access_token=fields['access_token'], id_token=fields['id_token'], refresh_token=fields['refresh_token'], created=time.time(), profile_perimeter=brand, client_id=client_id)
